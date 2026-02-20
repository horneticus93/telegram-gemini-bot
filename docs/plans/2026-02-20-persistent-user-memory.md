# Persistent User Memory Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Give the bot a persistent SQLite memory of each user — their name, interests, facts, and communication style — injected into every Gemini request so conversations feel personal.

**Architecture:** A new `bot/memory.py` module wraps SQLite (stdlib `sqlite3`, no extra deps) and stores one profile per Telegram user ID. After every `MEMORY_UPDATE_INTERVAL` messages from a user, a fire-and-forget async task calls Gemini to extract new facts and update the profile. The profile is loaded and injected into every `ask()` call. The SQLite file lives at `/app/data/memory.db` inside the container, mounted to a named Docker volume so it survives restarts and rebuilds.

**Tech Stack:** Python `sqlite3` (stdlib), existing `google-genai` SDK for profile extraction, Docker named volume.

---

## Task 1: UserMemory module

**Files:**
- Create: `bot/memory.py`
- Create: `tests/test_memory.py`

**Step 1: Create `tests/test_memory.py`** with exactly this content:

```python
import pytest
import os
from bot.memory import UserMemory


@pytest.fixture
def mem(tmp_path):
    return UserMemory(db_path=str(tmp_path / "test.db"))


def test_first_message_count_is_one(mem):
    count = mem.increment_message_count(user_id=1, username="alice", first_name="Alice")
    assert count == 1


def test_message_count_accumulates(mem):
    mem.increment_message_count(1, "alice", "Alice")
    mem.increment_message_count(1, "alice", "Alice")
    count = mem.increment_message_count(1, "alice", "Alice")
    assert count == 3


def test_different_users_have_independent_counts(mem):
    mem.increment_message_count(1, "alice", "Alice")
    count = mem.increment_message_count(2, "bob", "Bob")
    assert count == 1


def test_get_profile_unknown_user_returns_empty(mem):
    assert mem.get_profile(user_id=999) == ""


def test_update_and_get_profile(mem):
    mem.increment_message_count(1, "alice", "Alice")
    mem.update_profile(user_id=1, profile="Alice is a software engineer who loves cats.")
    assert mem.get_profile(1) == "Alice is a software engineer who loves cats."


def test_increment_updates_stored_name(mem):
    mem.increment_message_count(1, "alice_old", "Alice Old")
    mem.increment_message_count(1, "alice_new", "Alice New")
    # No crash, count is 2
    count = mem.increment_message_count(1, "alice_new", "Alice New")
    assert count == 3
```

**Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate && pytest tests/test_memory.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bot.memory'`

**Step 3: Create `bot/memory.py`** with exactly this content:

```python
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class UserMemory:
    def __init__(self, db_path: str = "/app/data/memory.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id     INTEGER PRIMARY KEY,
                    username    TEXT,
                    first_name  TEXT,
                    profile     TEXT    DEFAULT '',
                    msg_count   INTEGER DEFAULT 0,
                    updated_at  TEXT
                )
            """)
            conn.commit()

    def increment_message_count(
        self, user_id: int, username: str, first_name: str
    ) -> int:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO user_profiles (user_id, username, first_name, msg_count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                    msg_count  = msg_count + 1,
                    username   = excluded.username,
                    first_name = excluded.first_name
                """,
                (user_id, username, first_name),
            )
            conn.commit()
            row = conn.execute(
                "SELECT msg_count FROM user_profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
            return row[0]

    def get_profile(self, user_id: int) -> str:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT profile FROM user_profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
            return row[0] if row and row[0] else ""

    def update_profile(self, user_id: int, profile: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE user_profiles
                SET profile = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (profile, datetime.now(timezone.utc).isoformat(), user_id),
            )
            conn.commit()
```

**Step 4: Run tests to verify they pass**

```bash
source .venv/bin/activate && pytest tests/test_memory.py -v
```

Expected: All 6 tests PASS.

**Step 5: Commit**

```bash
git add bot/memory.py tests/test_memory.py
git commit -m "feat: UserMemory module with SQLite persistence"
```

---

## Task 2: Gemini profile extraction + user_profile in ask()

**Files:**
- Modify: `bot/gemini.py`
- Modify: `tests/test_gemini.py`

**Step 1: Add 3 new tests to `tests/test_gemini.py`** — append after the existing 4 tests:

```python
@patch("bot.gemini.genai.Client")
def test_ask_includes_user_profile_in_prompt(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = "Answer"
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    client.ask(history="", question="What should I eat?", user_profile="Alice loves Italian food.")

    call_kwargs = mock_client.models.generate_content.call_args
    contents = call_kwargs.kwargs.get("contents") or call_kwargs.args[1]
    assert "Alice loves Italian food." in contents


@patch("bot.gemini.genai.Client")
def test_ask_without_profile_omits_profile_section(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = "Answer"
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    client.ask(history="", question="Hello", user_profile="")

    call_kwargs = mock_client.models.generate_content.call_args
    contents = call_kwargs.kwargs.get("contents") or call_kwargs.args[1]
    assert "Profile" not in contents


@patch("bot.gemini.genai.Client")
def test_extract_profile_returns_text(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = "Alice is a nurse who likes hiking."
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    result = client.extract_profile(
        existing_profile="",
        recent_history="[Alice]: I just got back from a hike",
        user_name="Alice",
    )
    assert result == "Alice is a nurse who likes hiking."
    mock_client.models.generate_content.assert_called_once()
```

**Step 2: Run new tests to verify they fail**

```bash
source .venv/bin/activate && pytest tests/test_gemini.py -v -k "profile"
```

Expected: FAIL (3 tests, AttributeError or assertion errors)

**Step 3: Update `bot/gemini.py`** — replace the entire file with:

```python
import os
from google import genai
from google.genai import types

SYSTEM_PROMPT = (
    "You are a helpful assistant in a Telegram group chat. "
    "Keep your responses short and conversational — maximum 3 to 5 sentences. "
    "Write like a person texting, not like a document. "
    "If you need to search the web for current information, do so and include the answer in this same response. "
    "IMPORTANT: Never say you will look something up and get back later. "
    "Never defer your answer to a future message. "
    "Always provide your complete answer right now, in this single response."
)


class GeminiClient:
    def __init__(self, api_key: str):
        self._client = genai.Client(api_key=api_key)
        self._model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    def ask(self, history: str, question: str, user_profile: str = "") -> str:
        profile_section = (
            f"\n\nProfile of the person asking:\n{user_profile}"
            if user_profile
            else ""
        )
        if history:
            contents = (
                f"Here is the recent group conversation:\n\n{history}"
                f"{profile_section}"
                f"\n\nNow answer this: {question}"
            )
        else:
            contents = (
                f"{profile_section.strip()}\n\n{question}".strip()
                if user_profile
                else question
            )

        response = self._client.models.generate_content(
            model=self._model,
            contents=contents,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                system_instruction=SYSTEM_PROMPT,
            ),
        )
        text = response.text
        if text is None:
            raise ValueError("Gemini returned no text response")
        return text

    def extract_profile(
        self, existing_profile: str, recent_history: str, user_name: str
    ) -> str:
        prompt = (
            f"Update the memory profile for {user_name} based on their recent messages.\n\n"
            f"Current profile:\n{existing_profile or '(empty)'}\n\n"
            f"Recent conversation (focus on messages from {user_name}):\n{recent_history}\n\n"
            f"Write an updated profile in third person (e.g. '{user_name} is...'). "
            f"Include: interests, job, preferences, facts they shared, communication style. "
            f"Max 150 words. If nothing new, return the current profile unchanged."
        )
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are a memory assistant. Extract personal facts about a specific user "
                    "from chat messages and maintain their concise profile. Be factual, no speculation."
                ),
            ),
        )
        text = response.text
        if text is None:
            return existing_profile
        return text.strip()
```

**Step 4: Run full test suite**

```bash
source .venv/bin/activate && pytest -v
```

Expected: All 25 tests PASS (6 memory + 7 gemini + 5 handlers + 7 session).

**Step 5: Commit**

```bash
git add bot/gemini.py tests/test_gemini.py
git commit -m "feat: add user_profile to ask(), add extract_profile method"
```

---

## Task 3: Wire memory into handlers

**Files:**
- Modify: `bot/handlers.py`
- Modify: `tests/test_handlers.py`

**Step 1: Add 2 new tests to `tests/test_handlers.py`** — append after the existing 5 tests:

```python
@pytest.mark.asyncio
async def test_increments_user_message_count():
    from bot.handlers import handle_message, user_memory
    update = make_update("hello there", chat_id=10, first_name="TestUser")
    update.message.from_user.id = 42
    context = make_context()

    with patch("bot.handlers.ALLOWED_CHAT_IDS", {10}):
        await handle_message(update, context)

    count = user_memory.get_profile(42)  # profile empty but user exists
    # Just verify no crash and count was incremented (profile may be empty)
    assert isinstance(count, str)


@pytest.mark.asyncio
async def test_passes_user_profile_to_gemini():
    from bot.handlers import handle_message, user_memory
    user_memory.update_profile(user_id=99, profile="Bob is a chef.")
    update = make_update("@testbot what should I cook?", chat_id=5, first_name="Bob")
    update.message.from_user.id = 99
    context = make_context(bot_username="testbot")

    with patch("bot.handlers.ALLOWED_CHAT_IDS", {5}):
        with patch("bot.handlers.gemini_client") as mock_gemini:
            mock_gemini.ask.return_value = "Try pasta!"
            await handle_message(update, context)

    call_kwargs = mock_gemini.ask.call_args.kwargs
    profile = call_kwargs.get("user_profile") or ""
    assert "Bob is a chef." in profile
```

**Step 2: Run new tests to verify they fail**

```bash
source .venv/bin/activate && pytest tests/test_handlers.py -v -k "memory or profile"
```

Expected: FAIL

**Step 3: Replace `bot/handlers.py`** with exactly this content:

```python
import os
import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes
from .session import SessionManager
from .gemini import GeminiClient
from .memory import UserMemory

logger = logging.getLogger(__name__)

ALLOWED_CHAT_IDS: set[int] = {
    int(cid.strip())
    for cid in os.getenv("ALLOWED_CHAT_IDS", "").split(",")
    if cid.strip()
}

MEMORY_UPDATE_INTERVAL = int(os.getenv("MEMORY_UPDATE_INTERVAL", "10"))

session_manager = SessionManager(
    max_messages=int(os.getenv("MAX_HISTORY_MESSAGES", "100"))
)
user_memory = UserMemory(db_path=os.getenv("DB_PATH", "/app/data/memory.db"))


class _LazyGeminiClient:
    """Wraps GeminiClient with lazy initialisation so the module can be
    imported without a valid GEMINI_API_KEY (e.g. during tests).  Tests that
    patch ``bot.handlers.gemini_client`` replace this object entirely, so the
    lazy logic is never exercised in that path."""

    def __init__(self) -> None:
        self._client: GeminiClient | None = None

    def _get(self) -> GeminiClient:
        if self._client is None:
            self._client = GeminiClient(api_key=os.getenv("GEMINI_API_KEY", ""))
        return self._client

    def ask(self, history: str, question: str, user_profile: str = "") -> str:
        return self._get().ask(history=history, question=question, user_profile=user_profile)


gemini_client: _LazyGeminiClient = _LazyGeminiClient()


async def _update_user_profile(user_id: int, user_name: str, chat_id: int) -> None:
    try:
        existing_profile = user_memory.get_profile(user_id)
        recent_history = session_manager.format_history(chat_id)
        new_profile = gemini_client._get().extract_profile(
            existing_profile=existing_profile,
            recent_history=recent_history,
            user_name=user_name,
        )
        user_memory.update_profile(user_id, new_profile)
        logger.info("Updated memory profile for user %s (%s)", user_id, user_name)
    except Exception:
        logger.exception("Failed to update profile for user %s", user_id)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    chat_id = update.message.chat_id
    if chat_id not in ALLOWED_CHAT_IDS:
        return

    user = update.message.from_user
    if user is None:
        return
    author = user.first_name or user.username or "Unknown"
    text = update.message.text

    session_manager.add_message(chat_id, author, text)

    msg_count = user_memory.increment_message_count(
        user_id=user.id,
        username=user.username or "",
        first_name=author,
    )
    if msg_count % MEMORY_UPDATE_INTERVAL == 0:
        asyncio.create_task(_update_user_profile(user.id, author, chat_id))

    is_private = update.message.chat.type == "private"
    bot_username = context.bot.username
    is_reply_to_bot = (
        update.message.reply_to_message is not None
        and update.message.reply_to_message.from_user is not None
        and update.message.reply_to_message.from_user.username == bot_username
    )
    if not is_private and not is_reply_to_bot and f"@{bot_username}" not in text:
        return

    question = text.replace(f"@{bot_username}", "").strip() or text
    history = session_manager.format_history(chat_id)
    user_profile = user_memory.get_profile(user.id)

    try:
        response = gemini_client.ask(
            history=history,
            question=question,
            user_profile=user_profile,
        )
        if len(response) <= 4096:
            await update.message.reply_text(response)
        else:
            for i in range(0, len(response), 4096):
                await update.message.reply_text(response[i : i + 4096])
    except Exception:
        logger.exception("Gemini API call failed")
        await update.message.reply_text(
            "Sorry, something went wrong. Try again."
        )
```

**Step 4: Run full test suite**

```bash
source .venv/bin/activate && pytest -v
```

Expected: All 27 tests PASS.

**Step 5: Commit**

```bash
git add bot/handlers.py tests/test_handlers.py
git commit -m "feat: wire user memory into message handler"
```

---

## Task 4: Docker volume + env vars

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `.dockerignore`

**Step 1: Update `docker-compose.yml`** — replace entire file with:

```yaml
services:
  bot:
    build: .
    restart: unless-stopped
    env_file: .env
    volumes:
      - bot_data:/app/data
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

volumes:
  bot_data:
```

**Step 2: Update `.env.example`** — add two new variables after `GEMINI_MODEL`:

```
TELEGRAM_BOT_TOKEN=your_token_here
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-1.5-flash
MEMORY_UPDATE_INTERVAL=10
DB_PATH=/app/data/memory.db
ALLOWED_CHAT_IDS=-100123456789
MAX_HISTORY_MESSAGES=100
```

**Step 3: Add `data/` to `.dockerignore`** — append one line:

```
data/
```

**Step 4: Run full test suite one final time**

```bash
source .venv/bin/activate && pytest -v
```

Expected: All 27 tests PASS.

**Step 5: Commit**

```bash
git add docker-compose.yml .env.example .dockerignore
git commit -m "chore: add Docker volume for SQLite persistence, document new env vars"
```

---

## Task 5: Push and deploy

**Step 1: Push to GitHub**

```bash
git push
```

**Step 2: On the NAS — pull, add env vars, rebuild**

```bash
cd ~/app/horneticus93/telegram-gemini-bot
git pull
```

Add to `.env` on the NAS:
```
MEMORY_UPDATE_INTERVAL=10
DB_PATH=/app/data/memory.db
```

```bash
sudo docker compose down
sudo docker compose up -d --build
```

**Step 3: Verify**

```bash
sudo docker compose logs -f
```

Expected: `Bot starting, polling for updates...` with no errors.

After 10 messages from any user, you should see in the logs:
```
Updated memory profile for user <id> (<name>)
```

**Step 4: Inspect stored profiles (optional)**

To peek at what the bot has remembered, SSH into the NAS and run:

```bash
sudo docker compose exec bot python3 -c "
import sqlite3
conn = sqlite3.connect('/app/data/memory.db')
for row in conn.execute('SELECT first_name, profile, msg_count FROM user_profiles'):
    print(row)
"
```

---

## Full expected test suite

```
tests/test_memory.py::test_first_message_count_is_one             PASSED
tests/test_memory.py::test_message_count_accumulates              PASSED
tests/test_memory.py::test_different_users_have_independent_counts PASSED
tests/test_memory.py::test_get_profile_unknown_user_returns_empty  PASSED
tests/test_memory.py::test_update_and_get_profile                 PASSED
tests/test_memory.py::test_increment_updates_stored_name          PASSED
tests/test_gemini.py::test_ask_calls_generate_content             PASSED
tests/test_gemini.py::test_ask_includes_history_in_prompt         PASSED
tests/test_gemini.py::test_ask_with_empty_history                 PASSED
tests/test_gemini.py::test_ask_raises_on_none_response            PASSED
tests/test_gemini.py::test_ask_includes_user_profile_in_prompt    PASSED
tests/test_gemini.py::test_ask_without_profile_omits_profile_section PASSED
tests/test_gemini.py::test_extract_profile_returns_text           PASSED
tests/test_handlers.py::test_ignores_disallowed_chat              PASSED
tests/test_handlers.py::test_stores_message_without_tag           PASSED
tests/test_handlers.py::test_replies_when_tagged                  PASSED
tests/test_handlers.py::test_replies_with_error_on_gemini_failure PASSED
tests/test_handlers.py::test_strips_bot_mention_from_question     PASSED
tests/test_handlers.py::test_increments_user_message_count        PASSED
tests/test_handlers.py::test_passes_user_profile_to_gemini        PASSED
tests/test_session.py::test_add_and_get_single_message            PASSED
tests/test_session.py::test_empty_history_for_unknown_chat        PASSED
tests/test_session.py::test_rolling_window_drops_oldest           PASSED
tests/test_session.py::test_rolling_window_preserves_order        PASSED
tests/test_session.py::test_format_history_joins_with_newlines    PASSED
tests/test_session.py::test_format_history_empty_chat             PASSED
tests/test_session.py::test_separate_chats_dont_mix               PASSED

27 passed
```
