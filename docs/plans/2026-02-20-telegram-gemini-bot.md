# Telegram Gemini Bot Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Python Telegram bot that reads group conversation history and responds with Gemini + Google Search when tagged.

**Architecture:** Single Python process using `python-telegram-bot` (async polling). All group messages are stored in an in-memory rolling buffer per chat. When the bot is mentioned (`@botname`), it sends the full buffer + question to Gemini with Search Grounding enabled, then replies concisely.

**Tech Stack:** Python 3.12, `python-telegram-bot>=21.0`, `google-genai>=1.0.0`, `python-dotenv`, Docker (`python:3.12-slim`), pytest + pytest-asyncio for tests.

---

## Task 1: Project Scaffolding

**Files:**
- Create: `bot/__init__.py`
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `pytest.ini`

**Step 1: Create `bot/__init__.py` (empty package marker)**

```python
```
(empty file)

**Step 2: Create `requirements.txt`**

```
python-telegram-bot>=21.0,<22.0
google-genai>=1.0.0
python-dotenv>=1.0.0
```

**Step 3: Create `requirements-dev.txt`**

```
-r requirements.txt
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

**Step 4: Create `.env.example`**

```
TELEGRAM_BOT_TOKEN=your_token_here
GEMINI_API_KEY=your_gemini_api_key_here
ALLOWED_CHAT_IDS=-100123456789
MAX_HISTORY_MESSAGES=100
```

**Step 5: Create `.gitignore`**

```
.env
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dist/
```

**Step 6: Create `pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
```

**Step 7: Install dev dependencies**

```bash
pip install -r requirements-dev.txt
```

Expected: All packages install without errors.

**Step 8: Commit**

```bash
git add bot/__init__.py requirements.txt requirements-dev.txt .env.example .gitignore pytest.ini
git commit -m "chore: project scaffolding and dependencies"
```

---

## Task 2: Session Manager

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_session.py`
- Create: `bot/session.py`

**Step 1: Create `tests/__init__.py`** (empty)

**Step 2: Write failing tests in `tests/test_session.py`**

```python
import pytest
from bot.session import SessionManager


def test_add_and_get_single_message():
    sm = SessionManager(max_messages=10)
    sm.add_message(chat_id=1, author="Alice", text="Hello")
    assert sm.get_history(1) == ["[Alice]: Hello"]


def test_empty_history_for_unknown_chat():
    sm = SessionManager(max_messages=10)
    assert sm.get_history(999) == []


def test_rolling_window_drops_oldest():
    sm = SessionManager(max_messages=3)
    sm.add_message(1, "A", "msg1")
    sm.add_message(1, "A", "msg2")
    sm.add_message(1, "A", "msg3")
    sm.add_message(1, "A", "msg4")  # should push out msg1
    history = sm.get_history(1)
    assert len(history) == 3
    assert "[A]: msg1" not in history
    assert "[A]: msg4" in history


def test_format_history_joins_with_newlines():
    sm = SessionManager(max_messages=10)
    sm.add_message(1, "Alice", "Hi")
    sm.add_message(1, "Bob", "Hey")
    result = sm.format_history(1)
    assert result == "[Alice]: Hi\n[Bob]: Hey"


def test_format_history_empty_chat():
    sm = SessionManager(max_messages=10)
    assert sm.format_history(999) == ""


def test_separate_chats_dont_mix():
    sm = SessionManager(max_messages=10)
    sm.add_message(1, "Alice", "chat1")
    sm.add_message(2, "Bob", "chat2")
    assert sm.get_history(1) == ["[Alice]: chat1"]
    assert sm.get_history(2) == ["[Bob]: chat2"]
```

**Step 3: Run tests to verify they fail**

```bash
pytest tests/test_session.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bot.session'`

**Step 4: Implement `bot/session.py`**

```python
from collections import deque


class SessionManager:
    def __init__(self, max_messages: int = 100):
        self.max_messages = max_messages
        self._sessions: dict[int, deque] = {}

    def add_message(self, chat_id: int, author: str, text: str) -> None:
        if chat_id not in self._sessions:
            self._sessions[chat_id] = deque(maxlen=self.max_messages)
        self._sessions[chat_id].append(f"[{author}]: {text}")

    def get_history(self, chat_id: int) -> list[str]:
        if chat_id not in self._sessions:
            return []
        return list(self._sessions[chat_id])

    def format_history(self, chat_id: int) -> str:
        return "\n".join(self.get_history(chat_id))
```

**Step 5: Run tests to verify they pass**

```bash
pytest tests/test_session.py -v
```

Expected: All 6 tests PASS.

**Step 6: Commit**

```bash
git add tests/__init__.py tests/test_session.py bot/session.py
git commit -m "feat: session manager with rolling history buffer"
```

---

## Task 3: Gemini Client

**Files:**
- Create: `tests/test_gemini.py`
- Create: `bot/gemini.py`

**Step 1: Write failing tests in `tests/test_gemini.py`**

```python
import pytest
from unittest.mock import MagicMock, patch
from bot.gemini import GeminiClient


@patch("bot.gemini.genai.Client")
def test_ask_calls_generate_content(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = "Paris is the capital of France."
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    result = client.ask(history="[Alice]: What's the capital of France?", question="What's the capital of France?")

    assert result == "Paris is the capital of France."
    mock_client.models.generate_content.assert_called_once()


@patch("bot.gemini.genai.Client")
def test_ask_includes_history_in_prompt(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = "Some answer"
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    client.ask(history="[Alice]: test history", question="test question")

    call_kwargs = mock_client.models.generate_content.call_args
    contents = call_kwargs.kwargs.get("contents") or call_kwargs.args[1]
    assert "[Alice]: test history" in contents
    assert "test question" in contents


@patch("bot.gemini.genai.Client")
def test_ask_with_empty_history(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = "Hello!"
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    result = client.ask(history="", question="Say hello")
    assert result == "Hello!"
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_gemini.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bot.gemini'`

**Step 3: Implement `bot/gemini.py`**

```python
from google import genai
from google.genai import types

SYSTEM_PROMPT = (
    "You are a helpful assistant in a Telegram group chat. "
    "Keep your responses short and conversational — maximum 3 to 5 sentences. "
    "Write like a person texting, not like a document. "
    "If you need to search the web for current information, do so, "
    "but still summarize briefly."
)


class GeminiClient:
    def __init__(self, api_key: str):
        self._client = genai.Client(api_key=api_key)
        self._model = "gemini-2.0-flash"

    def ask(self, history: str, question: str) -> str:
        if history:
            contents = (
                f"Here is the recent group conversation:\n\n{history}"
                f"\n\nNow answer this: {question}"
            )
        else:
            contents = question

        response = self._client.models.generate_content(
            model=self._model,
            contents=contents,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                system_instruction=SYSTEM_PROMPT,
            ),
        )
        return response.text
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_gemini.py -v
```

Expected: All 3 tests PASS.

**Step 5: Commit**

```bash
git add tests/test_gemini.py bot/gemini.py
git commit -m "feat: Gemini client with search grounding"
```

---

## Task 4: Message Handler

**Files:**
- Create: `tests/test_handlers.py`
- Create: `bot/handlers.py`

**Step 1: Write failing tests in `tests/test_handlers.py`**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, Message, User, Chat
from telegram.ext import ContextTypes


def make_update(text: str, chat_id: int, first_name: str = "Alice") -> Update:
    user = MagicMock(spec=User)
    user.first_name = first_name
    user.username = first_name.lower()

    message = MagicMock(spec=Message)
    message.text = text
    message.chat_id = chat_id
    message.from_user = user
    message.reply_text = AsyncMock()

    update = MagicMock(spec=Update)
    update.message = message
    return update


def make_context(bot_username: str = "testbot") -> ContextTypes.DEFAULT_TYPE:
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = MagicMock()
    context.bot.username = bot_username
    return context


@pytest.mark.asyncio
async def test_ignores_disallowed_chat():
    from bot.handlers import handle_message
    update = make_update("hello", chat_id=9999)
    context = make_context()

    with patch("bot.handlers.ALLOWED_CHAT_IDS", {1}):
        await handle_message(update, context)

    update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_stores_message_without_tag():
    from bot.handlers import handle_message, session_manager
    update = make_update("just chatting", chat_id=1)
    context = make_context()

    with patch("bot.handlers.ALLOWED_CHAT_IDS", {1}):
        await handle_message(update, context)

    update.message.reply_text.assert_not_called()
    history = session_manager.get_history(1)
    assert any("just chatting" in msg for msg in history)


@pytest.mark.asyncio
async def test_replies_when_tagged():
    from bot.handlers import handle_message
    update = make_update("@testbot what time is it?", chat_id=2)
    context = make_context(bot_username="testbot")

    with patch("bot.handlers.ALLOWED_CHAT_IDS", {2}):
        with patch("bot.handlers.gemini_client") as mock_gemini:
            mock_gemini.ask.return_value = "It's noon!"
            await handle_message(update, context)

    update.message.reply_text.assert_called_once_with("It's noon!")


@pytest.mark.asyncio
async def test_replies_with_error_on_gemini_failure():
    from bot.handlers import handle_message
    update = make_update("@testbot crash?", chat_id=3)
    context = make_context(bot_username="testbot")

    with patch("bot.handlers.ALLOWED_CHAT_IDS", {3}):
        with patch("bot.handlers.gemini_client") as mock_gemini:
            mock_gemini.ask.side_effect = Exception("API error")
            await handle_message(update, context)

    update.message.reply_text.assert_called_once()
    args = update.message.reply_text.call_args[0][0]
    assert "wrong" in args.lower() or "error" in args.lower() or "sorry" in args.lower()


@pytest.mark.asyncio
async def test_strips_bot_mention_from_question():
    from bot.handlers import handle_message
    update = make_update("@testbot what is 2+2?", chat_id=4)
    context = make_context(bot_username="testbot")

    with patch("bot.handlers.ALLOWED_CHAT_IDS", {4}):
        with patch("bot.handlers.gemini_client") as mock_gemini:
            mock_gemini.ask.return_value = "4"
            await handle_message(update, context)

    call_kwargs = mock_gemini.ask.call_args.kwargs
    question = call_kwargs.get("question") or mock_gemini.ask.call_args.args[1]
    assert "@testbot" not in question
    assert "2+2" in question
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_handlers.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bot.handlers'`

**Step 3: Implement `bot/handlers.py`**

```python
import os
import logging
from telegram import Update
from telegram.ext import ContextTypes
from .session import SessionManager
from .gemini import GeminiClient

logger = logging.getLogger(__name__)

ALLOWED_CHAT_IDS: set[int] = {
    int(cid.strip())
    for cid in os.getenv("ALLOWED_CHAT_IDS", "").split(",")
    if cid.strip()
}

session_manager = SessionManager(
    max_messages=int(os.getenv("MAX_HISTORY_MESSAGES", "100"))
)
gemini_client = GeminiClient(api_key=os.getenv("GEMINI_API_KEY", ""))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    chat_id = update.message.chat_id
    if chat_id not in ALLOWED_CHAT_IDS:
        return

    user = update.message.from_user
    author = user.first_name or user.username or "Unknown"
    text = update.message.text

    session_manager.add_message(chat_id, author, text)

    bot_username = context.bot.username
    if f"@{bot_username}" not in text:
        return

    question = text.replace(f"@{bot_username}", "").strip() or text
    history = session_manager.format_history(chat_id)

    try:
        response = gemini_client.ask(history=history, question=question)
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

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_handlers.py -v
```

Expected: All 5 tests PASS.

**Step 5: Run full test suite**

```bash
pytest -v
```

Expected: All 14 tests PASS.

**Step 6: Commit**

```bash
git add tests/test_handlers.py bot/handlers.py
git commit -m "feat: message handler with access control and Gemini integration"
```

---

## Task 5: Main Entry Point

**Files:**
- Create: `bot/main.py`

**Step 1: Implement `bot/main.py`**

No tests needed here — this is pure wiring of the framework.

```python
import os
import logging
from dotenv import load_dotenv
from telegram.ext import Application, MessageHandler, filters
from .handlers import handle_message

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")

    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot starting, polling for updates...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
```

**Step 2: Verify import works (no .env needed for import check)**

```bash
python -c "from bot.main import main; print('OK')"
```

Expected: `OK`

**Step 3: Commit**

```bash
git add bot/main.py
git commit -m "feat: main entry point with polling setup"
```

---

## Task 6: Docker Configuration

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

**Step 1: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "bot.main"]
```

**Step 2: Create `docker-compose.yml`**

```yaml
services:
  bot:
    build: .
    restart: unless-stopped
    env_file: .env
```

**Step 3: Verify Docker build works**

```bash
docker build -t telegram-gemini-bot .
```

Expected: Image builds successfully with no errors.

**Step 4: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "chore: Docker configuration for NAS deployment"
```

---

## Task 7: Local Smoke Test & Deployment Instructions

**Step 1: Create your `.env` from `.env.example`**

```bash
cp .env.example .env
```

Then fill in real values:
- `TELEGRAM_BOT_TOKEN` — get from [@BotFather](https://t.me/botfather) on Telegram
- `GEMINI_API_KEY` — get from [Google AI Studio](https://aistudio.google.com/app/apikey)
- `ALLOWED_CHAT_IDS` — leave empty for now; see Step 2

**Step 2: Find your group chat ID**

1. Add the bot to your Telegram group
2. Send any message in the group
3. Run:
```bash
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates"
```
4. Find `"chat": {"id": -100XXXXXXXXXX ...}` in the JSON — that negative number is your `ALLOWED_CHAT_IDS` value
5. Set it in `.env`

**Step 3: Run locally to verify**

```bash
python -m bot.main
```

Expected: `Bot starting, polling for updates...` — then send a message in the group tagging the bot and confirm it replies.

**Step 4: Run on NAS via Docker**

Copy the project to your NAS (via Synology File Station or `scp`), then SSH in:

```bash
cd /path/to/telegram-gemini-bot
docker compose up -d
```

Verify it's running:
```bash
docker compose logs -f
```

Expected: Continuous log output, no crash loops.

**Step 5: Final commit**

```bash
git add .env.example  # if any updates were made
git commit -m "docs: deployment instructions and smoke test notes"
```

---

## Full Test Suite

At any point, run all tests with:

```bash
pytest -v
```

Expected output:
```
tests/test_session.py::test_add_and_get_single_message PASSED
tests/test_session.py::test_empty_history_for_unknown_chat PASSED
tests/test_session.py::test_rolling_window_drops_oldest PASSED
tests/test_session.py::test_format_history_joins_with_newlines PASSED
tests/test_session.py::test_format_history_empty_chat PASSED
tests/test_session.py::test_separate_chats_dont_mix PASSED
tests/test_gemini.py::test_ask_calls_generate_content PASSED
tests/test_gemini.py::test_ask_includes_history_in_prompt PASSED
tests/test_gemini.py::test_ask_with_empty_history PASSED
tests/test_handlers.py::test_ignores_disallowed_chat PASSED
tests/test_handlers.py::test_stores_message_without_tag PASSED
tests/test_handlers.py::test_replies_when_tagged PASSED
tests/test_handlers.py::test_replies_with_error_on_gemini_failure PASSED
tests/test_handlers.py::test_strips_bot_mention_from_question PASSED

14 passed
```
