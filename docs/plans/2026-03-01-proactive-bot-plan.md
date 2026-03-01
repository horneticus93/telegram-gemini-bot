# Proactive Bot Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the bot proactive — it sends messages on its own: date congratulations, discussion starters, and silence-breaking responses.

**Architecture:** New `bot/scheduler.py` module uses python-telegram-bot's `JobQueue` to schedule three types of proactive jobs. A new `scheduled_events` SQLite table (via Alembic) stores structured dates. Gemini generates all proactive content. Safety mechanisms (daily limits, night mode) prevent spam.

**Tech Stack:** python-telegram-bot `JobQueue`, SQLite/Alembic, Gemini API, `zoneinfo` for timezone handling.

---

## Task 1: Alembic Migration — `scheduled_events` Table

**Files:**
- Create: `alembic/versions/a1b2c3d4e5f6_add_scheduled_events.py`

**Step 1: Create the migration file**

```python
"""add_scheduled_events

Revision ID: a1b2c3d4e5f6
Revises: b71d5f4a9c2e
Create Date: 2026-03-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "b71d5f4a9c2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduled_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER,
            chat_id         INTEGER NOT NULL,
            event_type      TEXT NOT NULL CHECK(event_type IN ('birthday', 'anniversary', 'custom')),
            event_date      TEXT NOT NULL,
            title           TEXT NOT NULL,
            source_fact_id  INTEGER,
            last_triggered  TEXT,
            is_active       INTEGER NOT NULL DEFAULT 1,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_scheduled_events_date ON scheduled_events(event_date)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_scheduled_events_chat ON scheduled_events(chat_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_scheduled_events_active ON scheduled_events(is_active)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS idx_scheduled_events_active")
    op.execute("DROP INDEX IF EXISTS idx_scheduled_events_chat")
    op.execute("DROP INDEX IF EXISTS idx_scheduled_events_date")
    op.execute("DROP TABLE IF EXISTS scheduled_events")
```

**Step 2: Run migration to verify**

Run: `alembic upgrade head`
Expected: Migration applies cleanly.

**Step 3: Commit**

```bash
git add alembic/versions/a1b2c3d4e5f6_add_scheduled_events.py
git commit -m "feat: add scheduled_events table migration"
```

---

## Task 2: Memory Layer — `scheduled_events` CRUD

**Files:**
- Modify: `bot/memory.py` (add methods after `get_chat_members` at line ~534)
- Test: `tests/test_memory.py`

**Step 1: Write failing tests**

Add to `tests/test_memory.py`:

```python
# --- scheduled_events tests ---

def test_upsert_scheduled_event_creates_new(memory):
    memory.upsert_scheduled_event(
        user_id=1,
        chat_id=-100,
        event_type="birthday",
        event_date="03-10",
        title="Oleksandr's birthday",
        source_fact_id=None,
    )
    events = memory.get_events_for_date("03-10")
    assert len(events) == 1
    assert events[0]["user_id"] == 1
    assert events[0]["event_type"] == "birthday"
    assert events[0]["title"] == "Oleksandr's birthday"


def test_upsert_scheduled_event_updates_existing(memory):
    memory.upsert_scheduled_event(
        user_id=1, chat_id=-100, event_type="birthday",
        event_date="03-10", title="Oleksandr's birthday",
    )
    memory.upsert_scheduled_event(
        user_id=1, chat_id=-100, event_type="birthday",
        event_date="03-15", title="Oleksandr's birthday (corrected)",
    )
    old = memory.get_events_for_date("03-10")
    new = memory.get_events_for_date("03-15")
    assert len(old) == 0
    assert len(new) == 1
    assert new[0]["title"] == "Oleksandr's birthday (corrected)"


def test_get_events_for_date_filters_inactive(memory):
    memory.upsert_scheduled_event(
        user_id=1, chat_id=-100, event_type="birthday",
        event_date="03-10", title="Birthday",
    )
    events = memory.get_events_for_date("03-10")
    assert len(events) == 1
    # Deactivate via direct SQL for testing
    import sqlite3
    with sqlite3.connect(memory.db_path) as conn:
        conn.execute("UPDATE scheduled_events SET is_active = 0")
        conn.commit()
    events = memory.get_events_for_date("03-10")
    assert len(events) == 0


def test_get_events_for_date_groups_by_chat(memory):
    memory.upsert_scheduled_event(
        user_id=1, chat_id=-100, event_type="birthday",
        event_date="03-10", title="Birthday A",
    )
    memory.upsert_scheduled_event(
        user_id=2, chat_id=-100, event_type="birthday",
        event_date="03-10", title="Birthday B",
    )
    memory.upsert_scheduled_event(
        user_id=3, chat_id=-200, event_type="birthday",
        event_date="03-10", title="Birthday C",
    )
    events = memory.get_events_for_date("03-10")
    assert len(events) == 3
    chat_100 = [e for e in events if e["chat_id"] == -100]
    chat_200 = [e for e in events if e["chat_id"] == -200]
    assert len(chat_100) == 2
    assert len(chat_200) == 1


def test_mark_event_triggered(memory):
    memory.upsert_scheduled_event(
        user_id=1, chat_id=-100, event_type="birthday",
        event_date="03-10", title="Birthday",
    )
    events = memory.get_events_for_date("03-10")
    event_id = events[0]["id"]
    memory.mark_event_triggered(event_id)
    events_after = memory.get_events_for_date("03-10")
    # Should still show up (last_triggered is set but it's still active)
    assert len(events_after) == 1
    assert events_after[0]["last_triggered"] is not None
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_memory.py -k "scheduled_event" -v`
Expected: FAIL — `UserMemory` has no `upsert_scheduled_event` method.

**Step 3: Implement the methods**

Add to `bot/memory.py` class `UserMemory` (after `get_chat_members`):

```python
def upsert_scheduled_event(
    self,
    user_id: int | None,
    chat_id: int,
    event_type: str,
    event_date: str,
    title: str,
    source_fact_id: int | None = None,
) -> None:
    """Create or update a scheduled event. Deduplicates by user_id + chat_id + event_type."""
    now = _now_iso()
    with sqlite3.connect(self.db_path) as conn:
        existing = conn.execute(
            """
            SELECT id FROM scheduled_events
            WHERE COALESCE(user_id, -1) = COALESCE(?, -1)
              AND chat_id = ?
              AND event_type = ?
              AND is_active = 1
            """,
            (user_id, chat_id, event_type),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE scheduled_events
                SET event_date = ?, title = ?, source_fact_id = COALESCE(?, source_fact_id),
                    updated_at = ?
                WHERE id = ?
                """,
                (event_date, title, source_fact_id, now, existing[0]),
            )
        else:
            conn.execute(
                """
                INSERT INTO scheduled_events (
                    user_id, chat_id, event_type, event_date, title,
                    source_fact_id, last_triggered, is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, 1, ?, ?)
                """,
                (user_id, chat_id, event_type, event_date, title, source_fact_id, now, now),
            )
        conn.commit()

def get_events_for_date(self, date_mmdd: str) -> list[dict]:
    """Return all active events matching MM-DD date string."""
    with sqlite3.connect(self.db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, chat_id, event_type, event_date,
                   title, source_fact_id, last_triggered
            FROM scheduled_events
            WHERE is_active = 1
              AND (event_date = ? OR event_date LIKE ?)
            ORDER BY chat_id, event_type
            """,
            (date_mmdd, f"%-{date_mmdd}"),
        ).fetchall()
    return [
        {
            "id": r[0], "user_id": r[1], "chat_id": r[2],
            "event_type": r[3], "event_date": r[4], "title": r[5],
            "source_fact_id": r[6], "last_triggered": r[7],
        }
        for r in rows
    ]

def mark_event_triggered(self, event_id: int) -> None:
    """Set last_triggered to now for the given event."""
    with sqlite3.connect(self.db_path) as conn:
        conn.execute(
            "UPDATE scheduled_events SET last_triggered = ? WHERE id = ?",
            (_now_iso(), event_id),
        )
        conn.commit()
```

**Step 4: Update conftest.py to clean `scheduled_events`**

In `tests/conftest.py`, add `scheduled_events` to the cleanup queries (lines 26, 32):

```python
conn.execute("DELETE FROM scheduled_events")
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_memory.py -k "scheduled_event" -v`
Expected: All 5 new tests PASS.

**Step 6: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS (including old ones).

**Step 7: Commit**

```bash
git add bot/memory.py tests/test_memory.py tests/conftest.py
git commit -m "feat: add scheduled_events CRUD methods to UserMemory"
```

---

## Task 3: Gemini — Date Extraction from Facts

**Files:**
- Modify: `bot/gemini.py` (add `extract_date_from_fact` method after `embed_text` at line ~299)
- Test: `tests/test_gemini.py`

**Step 1: Write failing tests**

Add to `tests/test_gemini.py`:

```python
def test_extract_date_from_fact_returns_date(client):
    """extract_date_from_fact returns structured date info when fact contains a date."""
    client._client.models.generate_content.return_value = MagicMock(
        text='{"event_type":"birthday","event_date":"03-10","title":"Oleksandr\'s birthday"}'
    )
    result = client.extract_date_from_fact("Oleksandr's birthday is March 10")
    assert result is not None
    assert result["event_type"] == "birthday"
    assert result["event_date"] == "03-10"


def test_extract_date_from_fact_returns_none_for_no_date(client):
    """extract_date_from_fact returns None when fact has no date."""
    client._client.models.generate_content.return_value = MagicMock(text="null")
    result = client.extract_date_from_fact("Oleksandr likes pizza")
    assert result is None


def test_extract_date_from_fact_handles_bad_json(client):
    """extract_date_from_fact returns None on invalid JSON."""
    client._client.models.generate_content.return_value = MagicMock(text="not json")
    result = client.extract_date_from_fact("some fact")
    assert result is None
```

Note: `client` fixture should already exist in `test_gemini.py` — it's a `GeminiClient` with mocked `_client`.

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gemini.py -k "extract_date_from_fact" -v`
Expected: FAIL — method doesn't exist.

**Step 3: Implement `extract_date_from_fact`**

Add to `GeminiClient` in `bot/gemini.py` (after `embed_text`):

```python
def extract_date_from_fact(self, fact_text: str) -> dict | None:
    """Check if a fact contains a date event. Returns dict or None.

    Returns:
        ``{"event_type": "birthday"|"anniversary"|"custom",
           "event_date": "MM-DD" or "YYYY-MM-DD",
           "title": "..."}``
        or ``None`` if the fact has no actionable date.
    """
    if not fact_text.strip():
        return None
    prompt = (
        f"Analyze this fact and determine if it contains a recurring date event "
        f"(birthday, anniversary, or other annual event).\n\n"
        f"Fact: {fact_text}\n\n"
        "If YES, return a JSON object:\n"
        '{"event_type":"birthday"|"anniversary"|"custom", '
        '"event_date":"MM-DD", "title":"short description"}\n\n'
        "If NO date event found, return exactly: null\n\n"
        "Rules:\n"
        "1. event_date must be MM-DD format (e.g. 03-10 for March 10).\n"
        "2. title should be a brief human-readable label.\n"
        "3. No markdown, no explanations."
    )
    response = self._client.models.generate_content(
        model=self._model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction="You are a strict date extraction system. Output valid JSON or null only.",
        ),
    )
    text = (response.text or "").strip()
    if not text or text == "null":
        return None
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            return None
        if not all(k in data for k in ("event_type", "event_date", "title")):
            return None
        if data["event_type"] not in {"birthday", "anniversary", "custom"}:
            data["event_type"] = "custom"
        return data
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
```

**Step 4: Add `extract_date_from_fact` to `_LazyGeminiClient` in `bot/handlers.py`**

Add after `decide_fact_action` method (around line 92):

```python
def extract_date_from_fact(self, fact_text: str) -> dict | None:
    return self._get().extract_date_from_fact(fact_text)
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_gemini.py -k "extract_date_from_fact" -v`
Expected: All 3 new tests PASS.

**Step 6: Commit**

```bash
git add bot/gemini.py bot/handlers.py tests/test_gemini.py
git commit -m "feat: add extract_date_from_fact to GeminiClient"
```

---

## Task 4: Auto-Extract Dates from New Facts

**Files:**
- Modify: `bot/handlers.py` — `_update_user_profile` function (lines 97-160)
- Test: `tests/test_handlers.py`

**Step 1: Write failing test**

Add to `tests/test_handlers.py`:

```python
@pytest.mark.asyncio
async def test_date_extraction_runs_after_fact_upsert(mock_update, mock_context):
    """When facts are upserted, extract_date_from_fact is called for each."""
    mock_update.message.chat.type = "private"
    mock_update.message.chat_id = ALLOWED_CHAT_ID

    with (
        patch("bot.handlers.gemini_client") as mock_gemini,
        patch("bot.handlers.user_memory") as mock_memory,
        patch("bot.handlers.session_manager"),
        patch("bot.handlers.MEMORY_UPDATE_INTERVAL", 1),
    ):
        mock_memory.increment_message_count.return_value = 1
        mock_gemini.extract_facts.return_value = [
            {"fact": "Oleksandr's birthday is March 10", "importance": 0.9, "confidence": 0.9, "scope": "user"},
        ]
        mock_gemini.embed_text.return_value = [0.1] * 768
        mock_gemini.decide_fact_action.return_value = {"action": "keep_add_new", "target_fact_id": None}
        mock_gemini.extract_date_from_fact.return_value = {
            "event_type": "birthday", "event_date": "03-10", "title": "Oleksandr's birthday",
        }
        mock_memory.find_similar_facts.return_value = []
        mock_gemini.ask.return_value = ("Hi!", False)

        await handle_message(mock_update, mock_context)
        # Wait for background task
        await asyncio.sleep(0.1)

        mock_gemini.extract_date_from_fact.assert_called_once_with(
            "Oleksandr's birthday is March 10"
        )
        mock_memory.upsert_scheduled_event.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_handlers.py -k "date_extraction" -v`
Expected: FAIL — `extract_date_from_fact` never called.

**Step 3: Modify `_update_user_profile` in `bot/handlers.py`**

After facts are upserted (lines 154-157), add date extraction loop. Insert after line 157 (`logger.info`):

```python
        # Extract dates from newly created facts for proactive scheduling
        for item in extracted_facts:
            fact_text = str(item.get("fact", "")).strip()
            if not fact_text:
                continue
            date_info = gemini_client.extract_date_from_fact(fact_text)
            if date_info:
                user_memory.upsert_scheduled_event(
                    user_id=user_id,
                    chat_id=chat_id,
                    event_type=date_info["event_type"],
                    event_date=date_info["event_date"],
                    title=date_info["title"],
                )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_handlers.py -k "date_extraction" -v`
Expected: PASS.

**Step 5: Run full handler tests**

Run: `pytest tests/test_handlers.py -v`
Expected: All tests PASS.

**Step 6: Commit**

```bash
git add bot/handlers.py tests/test_handlers.py
git commit -m "feat: auto-extract dates from facts into scheduled_events"
```

---

## Task 5: Gemini — Proactive Content Generation Methods

**Files:**
- Modify: `bot/gemini.py` (add 3 new methods)
- Test: `tests/test_gemini.py`

**Step 1: Write failing tests**

Add to `tests/test_gemini.py`:

```python
def test_generate_congratulation(client):
    """generate_congratulation returns a congratulation message."""
    client._client.models.generate_content.return_value = MagicMock(
        text="Happy birthday, Oleksandr! Hope your day is amazing!"
    )
    result = client.generate_congratulation(
        event_type="birthday",
        persons=[{"name": "Oleksandr", "user_id": 1, "username": "olex"}],
        person_facts={"1": ["loves pizza", "works as developer"]},
    )
    assert "birthday" in result.lower() or len(result) > 10


def test_generate_engagement(client):
    """generate_engagement returns a JSON with message and optional target_user_id."""
    client._client.models.generate_content.return_value = MagicMock(
        text='{"message": "Hey everyone, what movie should we watch?", "target_user_id": null}'
    )
    result = client.generate_engagement(
        members=[{"name": "Oleksandr", "user_id": 1}],
        member_facts={"1": ["loves sci-fi movies"]},
        recent_history="Oleksandr: I watched Dune yesterday",
    )
    assert "message" in result
    assert "target_user_id" in result


def test_generate_engagement_bad_json_fallback(client):
    """generate_engagement falls back on bad JSON."""
    client._client.models.generate_content.return_value = MagicMock(
        text="Hey what is going on guys?"
    )
    result = client.generate_engagement(
        members=[], member_facts={}, recent_history="",
    )
    assert result["message"] == "Hey what is going on guys?"
    assert result["target_user_id"] is None


def test_generate_silence_response(client):
    """generate_silence_response returns a text string."""
    client._client.models.generate_content.return_value = MagicMock(
        text="That's an interesting point about AI, what do you think?"
    )
    result = client.generate_silence_response(
        recent_messages=[{"author": "Oleksandr [ID: 1]", "text": "AI is getting crazy"}],
        author_facts={"1": ["interested in technology"]},
    )
    assert isinstance(result, str)
    assert len(result) > 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_gemini.py -k "generate_congratulation or generate_engagement or generate_silence" -v`
Expected: FAIL — methods don't exist.

**Step 3: Implement the three methods**

Add to `GeminiClient` in `bot/gemini.py` (after `extract_date_from_fact`):

```python
def generate_congratulation(
    self,
    event_type: str,
    persons: list[dict],
    person_facts: dict[str, list[str]],
) -> str:
    """Generate a personalized congratulation message.

    Args:
        event_type: 'birthday', 'anniversary', or 'custom'.
        persons: List of dicts with 'name', 'user_id', 'username'.
        person_facts: Dict mapping user_id (str) to list of fact strings.
    """
    persons_block = "\n".join(
        f"- {p['name']} (@{p.get('username', 'unknown')}): "
        + ", ".join(person_facts.get(str(p["user_id"]), ["no known facts"]))
        for p in persons
    )
    prompt = (
        f"Write a short, warm {event_type} congratulation for a Telegram group chat.\n\n"
        f"People to congratulate:\n{persons_block}\n\n"
        "Rules:\n"
        "1. Keep it short (2-4 sentences), casual Telegram style.\n"
        "2. Personalize using the known facts about each person.\n"
        "3. If multiple people, congratulate them together in one message.\n"
        "4. Be creative and fun, not generic.\n"
        "5. Do NOT use JSON format. Just write the message text directly."
    )
    response = self._client.models.generate_content(
        model=self._model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=(
                "You are a fun, friendly Telegram chat bot writing a congratulation. "
                "Be warm and personal. Output plain text only."
            ),
        ),
    )
    return (response.text or "Congratulations!").strip()

def generate_engagement(
    self,
    members: list[dict],
    member_facts: dict[str, list[str]],
    recent_history: str,
) -> dict:
    """Generate a discussion starter or personal question.

    Returns:
        ``{"message": "...", "target_user_id": int | None}``
    """
    members_block = "\n".join(
        f"- {m['name']} [ID: {m['user_id']}]: "
        + ", ".join(member_facts.get(str(m["user_id"]), ["no known facts"]))
        for m in members
    ) or "(no members)"
    prompt = (
        "You are a member of a Telegram group chat. Start an interesting conversation.\n\n"
        f"Chat members:\n{members_block}\n\n"
        f"Recent conversation:\n{recent_history or '(no recent messages)'}\n\n"
        "Choose ONE approach:\n"
        "A) Ask an interesting question to the whole group based on their interests\n"
        "B) Address one specific person with a personal question based on their known facts\n"
        "C) Share something interesting related to recent discussion topics\n\n"
        "Return JSON: {\"message\": \"your message\", \"target_user_id\": <user_id or null>}\n"
        "If targeting a specific person, set target_user_id to their ID number.\n"
        "Keep message short (1-3 sentences), casual Telegram tone.\n"
        "No markdown, no explanations — raw JSON only."
    )
    response = self._client.models.generate_content(
        model=self._model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=(
                "You are a fun group chat member starting conversation. "
                "Output valid JSON only."
            ),
        ),
    )
    text = (response.text or "").strip()
    if not text:
        return {"message": "", "target_user_id": None}
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "message" in data:
            target = data.get("target_user_id")
            try:
                target = int(target) if target is not None else None
            except (TypeError, ValueError):
                target = None
            return {"message": str(data["message"]), "target_user_id": target}
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return {"message": text, "target_user_id": None}

def generate_silence_response(
    self,
    recent_messages: list[dict],
    author_facts: dict[str, list[str]],
) -> str:
    """Generate a response to break chat silence.

    Args:
        recent_messages: List of dicts with 'author' and 'text'.
        author_facts: Dict mapping user_id (str) to list of fact strings.
    """
    history_block = "\n".join(
        f"{m['author']}: {m['text']}" for m in recent_messages[-20:]
    ) or "(no recent messages)"
    facts_block = "\n".join(
        f"- User {uid}: {', '.join(facts)}"
        for uid, facts in author_facts.items()
        if facts
    ) or "(no known facts)"
    prompt = (
        "You are a member of a Telegram group chat. The chat has been quiet for a while. "
        "Write a natural follow-up to the conversation.\n\n"
        f"Recent messages:\n{history_block}\n\n"
        f"Known facts about participants:\n{facts_block}\n\n"
        "Choose ONE approach:\n"
        "A) React to or continue the last topic discussed\n"
        "B) Ask a follow-up question about something someone said\n"
        "C) Bring up a new topic related to participants' interests\n\n"
        "Rules:\n"
        "1. Keep it short (1-2 sentences), casual Telegram tone.\n"
        "2. Sound natural, like a real person would.\n"
        "3. Do NOT use JSON. Output plain text only."
    )
    response = self._client.models.generate_content(
        model=self._model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=(
                "You are a casual group chat member. "
                "Write naturally, short messages. Output plain text only."
            ),
        ),
    )
    return (response.text or "").strip()
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_gemini.py -k "generate_congratulation or generate_engagement or generate_silence" -v`
Expected: All 4 new tests PASS.

**Step 5: Commit**

```bash
git add bot/gemini.py tests/test_gemini.py
git commit -m "feat: add Gemini methods for proactive content generation"
```

---

## Task 6: Scheduler Module — Core Logic

**Files:**
- Create: `bot/scheduler.py`
- Test: `tests/test_scheduler.py`

**Step 1: Write failing tests**

Create `tests/test_scheduler.py`:

```python
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.scheduler import (
    ProactiveScheduler,
    PROACTIVE_ENABLED,
)


@pytest.fixture
def scheduler():
    with (
        patch("bot.scheduler.user_memory") as mock_memory,
        patch("bot.scheduler.gemini_client") as mock_gemini,
        patch("bot.scheduler.session_manager") as mock_session,
    ):
        s = ProactiveScheduler()
        s._memory = mock_memory
        s._gemini = mock_gemini
        s._session = mock_session
        yield s


class TestDailyLimit:
    def test_can_send_when_under_limit(self, scheduler):
        assert scheduler._can_send(chat_id=-100) is True

    def test_cannot_send_when_at_limit(self, scheduler):
        scheduler._daily_limit = 2
        scheduler._daily_counts[-100] = 2
        assert scheduler._can_send(chat_id=-100) is False

    def test_record_sent_increments_count(self, scheduler):
        scheduler._record_sent(chat_id=-100)
        assert scheduler._daily_counts[-100] == 1
        scheduler._record_sent(chat_id=-100)
        assert scheduler._daily_counts[-100] == 2


class TestNightMode:
    def test_night_mode_blocks_at_night(self, scheduler):
        night_time = datetime(2026, 3, 1, 2, 0)  # 2 AM
        assert scheduler._is_night_time(night_time) is True

    def test_night_mode_allows_daytime(self, scheduler):
        day_time = datetime(2026, 3, 1, 10, 0)  # 10 AM
        assert scheduler._is_night_time(day_time) is False

    def test_night_mode_boundary_8am(self, scheduler):
        boundary = datetime(2026, 3, 1, 8, 0)  # 8 AM exactly
        assert scheduler._is_night_time(boundary) is False

    def test_night_mode_boundary_23pm(self, scheduler):
        boundary = datetime(2026, 3, 1, 23, 0)  # 11 PM exactly
        assert scheduler._is_night_time(boundary) is True


class TestCheckDates:
    @pytest.mark.asyncio
    async def test_check_dates_sends_congratulation(self, scheduler):
        scheduler._memory.get_events_for_date.return_value = [
            {"id": 1, "user_id": 1, "chat_id": -100, "event_type": "birthday",
             "title": "Olex birthday", "last_triggered": None},
        ]
        scheduler._memory.get_user_facts.return_value = ["loves pizza"]
        scheduler._memory.get_chat_members.return_value = [(1, "Oleksandr")]
        scheduler._gemini.generate_congratulation.return_value = "Happy birthday Oleksandr!"

        bot = AsyncMock()
        # Mock the get_chat method to return a chat with members
        member = MagicMock()
        member.user = MagicMock()
        member.user.id = 1
        member.user.username = "olex"

        await scheduler.check_dates(bot)

        bot.send_message.assert_called_once()
        call_args = bot.send_message.call_args
        assert call_args.kwargs["chat_id"] == -100
        assert "birthday" in call_args.kwargs["text"].lower() or "Oleksandr" in call_args.kwargs["text"]
        scheduler._memory.mark_event_triggered.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_check_dates_skips_already_triggered_today(self, scheduler):
        today_iso = datetime.now().isoformat()
        scheduler._memory.get_events_for_date.return_value = [
            {"id": 1, "user_id": 1, "chat_id": -100, "event_type": "birthday",
             "title": "Olex birthday", "last_triggered": today_iso},
        ]
        bot = AsyncMock()
        await scheduler.check_dates(bot)
        bot.send_message.assert_not_called()


class TestResetDailyCounts:
    def test_reset_clears_counts(self, scheduler):
        scheduler._daily_counts[-100] = 5
        scheduler._daily_counts[-200] = 3
        scheduler.reset_daily_counts()
        assert len(scheduler._daily_counts) == 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scheduler.py -v`
Expected: FAIL — `bot.scheduler` doesn't exist.

**Step 3: Create `bot/scheduler.py`**

```python
import logging
import os
import random
from collections import defaultdict
from datetime import datetime, date
from zoneinfo import ZoneInfo

from .memory import UserMemory
from .session import SessionManager
from .handlers import gemini_client as _handlers_gemini

logger = logging.getLogger(__name__)

PROACTIVE_ENABLED = os.getenv("PROACTIVE_ENABLED", "false").lower() == "true"
PROACTIVE_TIMEZONE = ZoneInfo(os.getenv("PROACTIVE_TIMEZONE", "Europe/Kyiv"))
PROACTIVE_DAILY_LIMIT = int(os.getenv("PROACTIVE_DAILY_LIMIT", "4"))
PROACTIVE_SILENCE_MINUTES = int(os.getenv("PROACTIVE_SILENCE_MINUTES", "7"))
PROACTIVE_SILENCE_PROBABILITY = float(os.getenv("PROACTIVE_SILENCE_PROBABILITY", "0.5"))

user_memory = UserMemory(db_path=os.getenv("DB_PATH", "/app/data/memory.db"))
session_manager: SessionManager | None = None  # set by register_jobs
gemini_client = _handlers_gemini


class ProactiveScheduler:
    def __init__(self) -> None:
        self._daily_limit = PROACTIVE_DAILY_LIMIT
        self._daily_counts: dict[int, int] = defaultdict(int)
        self._silence_jobs: dict[int, object] = {}  # chat_id -> Job
        self._memory = user_memory
        self._gemini = gemini_client
        self._session: SessionManager | None = None

    def _can_send(self, chat_id: int) -> bool:
        return self._daily_counts[chat_id] < self._daily_limit

    def _record_sent(self, chat_id: int) -> None:
        self._daily_counts[chat_id] += 1

    def _is_night_time(self, now: datetime) -> bool:
        """Check if it's night time (23:00-08:00) in the configured timezone."""
        return now.hour >= 23 or now.hour < 8

    def reset_daily_counts(self) -> None:
        self._daily_counts.clear()

    async def check_dates(self, bot) -> None:
        """Check for today's events and send congratulations."""
        now = datetime.now(PROACTIVE_TIMEZONE)
        if self._is_night_time(now):
            return

        today_mmdd = now.strftime("%m-%d")
        events = self._memory.get_events_for_date(today_mmdd)
        if not events:
            return

        # Filter out already triggered today
        today_date = now.date().isoformat()
        pending_events = []
        for event in events:
            last = event.get("last_triggered")
            if last and last[:10] == today_date:
                continue
            pending_events.append(event)

        if not pending_events:
            return

        # Group by (chat_id, event_type)
        groups: dict[tuple[int, str], list[dict]] = defaultdict(list)
        for event in pending_events:
            key = (event["chat_id"], event["event_type"])
            groups[key].append(event)

        for (chat_id, event_type), group_events in groups.items():
            if not self._can_send(chat_id):
                continue

            # Gather person info
            persons = []
            person_facts: dict[str, list[str]] = {}
            for event in group_events:
                uid = event["user_id"]
                members = self._memory.get_chat_members(chat_id)
                name = next((n for mid, n in members if mid == uid), "Unknown")
                persons.append({"name": name, "user_id": uid, "username": ""})
                facts = self._memory.get_user_facts(user_id=uid, limit=5)
                person_facts[str(uid)] = facts

            try:
                message = self._gemini.generate_congratulation(
                    event_type=event_type,
                    persons=persons,
                    person_facts=person_facts,
                )
                if message:
                    await bot.send_message(chat_id=chat_id, text=message)
                    self._record_sent(chat_id)
                    for event in group_events:
                        self._memory.mark_event_triggered(event["id"])
            except Exception:
                logger.exception("Failed to send congratulation to chat %s", chat_id)

    async def run_engagement(self, bot, chat_id: int) -> None:
        """Generate and send an engagement message to a chat."""
        now = datetime.now(PROACTIVE_TIMEZONE)
        if self._is_night_time(now) or not self._can_send(chat_id):
            return

        # 70% probability
        if random.random() > 0.7:
            return

        members_raw = self._memory.get_chat_members(chat_id)
        if not members_raw:
            return

        members = [{"name": name, "user_id": uid} for uid, name in members_raw]
        member_facts: dict[str, list[str]] = {}
        for uid, _ in members_raw:
            facts = self._memory.get_user_facts(user_id=uid, limit=5)
            member_facts[str(uid)] = facts

        recent_history = ""
        if self._session:
            recent_history = self._session.format_history(chat_id)

        try:
            result = self._gemini.generate_engagement(
                members=members,
                member_facts=member_facts,
                recent_history=recent_history,
            )
            message = result.get("message", "")
            if not message:
                return

            target_uid = result.get("target_user_id")
            if target_uid:
                # Find username for mention
                target_name = next(
                    (n for uid, n in members_raw if uid == target_uid), None
                )
                if target_name and not message.startswith("@"):
                    # Prepend mention if Gemini didn't include it
                    pass  # Gemini prompt already handles this

            await bot.send_message(chat_id=chat_id, text=message)
            self._record_sent(chat_id)
        except Exception:
            logger.exception("Failed to send engagement to chat %s", chat_id)

    async def break_silence(self, bot, chat_id: int) -> None:
        """Respond to chat silence with a natural message."""
        now = datetime.now(PROACTIVE_TIMEZONE)
        if self._is_night_time(now) or not self._can_send(chat_id):
            return

        if random.random() > PROACTIVE_SILENCE_PROBABILITY:
            return

        if not self._session:
            return

        history = self._session.get_history(chat_id)
        if not history:
            return

        recent = history[-20:]
        # Gather facts for recent authors
        author_facts: dict[str, list[str]] = {}
        seen_ids: set[str] = set()
        for msg in recent:
            author = msg.get("author", "")
            # Extract ID from "Name [ID: 123]" format
            if "[ID: " in author:
                uid = author.split("[ID: ")[1].rstrip("]")
                if uid not in seen_ids:
                    seen_ids.add(uid)
                    try:
                        facts = self._memory.get_user_facts(user_id=int(uid), limit=5)
                        author_facts[uid] = facts
                    except (ValueError, TypeError):
                        pass

        try:
            message = self._gemini.generate_silence_response(
                recent_messages=[{"author": m.get("author", ""), "text": m["text"]} for m in recent],
                author_facts=author_facts,
            )
            if message:
                await bot.send_message(chat_id=chat_id, text=message)
                self._record_sent(chat_id)
        except Exception:
            logger.exception("Failed to break silence in chat %s", chat_id)


# Module-level singleton
_scheduler = ProactiveScheduler()


async def check_dates_callback(context) -> None:
    """JobQueue callback for daily date check."""
    await _scheduler.check_dates(context.bot)


async def engagement_callback(context) -> None:
    """JobQueue callback for engagement messages."""
    chat_id = context.job.data
    await _scheduler.run_engagement(context.bot, chat_id)


async def silence_callback(context) -> None:
    """JobQueue callback for silence breaking."""
    chat_id = context.job.data
    await _scheduler.break_silence(context.bot, chat_id)


async def reset_daily_counts_callback(context) -> None:
    """JobQueue callback to reset daily proactive message counts at midnight."""
    _scheduler.reset_daily_counts()


def reset_silence_timer(job_queue, chat_id: int) -> None:
    """Reset the silence timer for a chat. Called from handle_message."""
    if not PROACTIVE_ENABLED:
        return

    # Remove existing silence job for this chat
    job_name = f"silence_{chat_id}"
    current_jobs = job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()

    # Schedule new silence job with random delay
    delay_seconds = random.randint(
        PROACTIVE_SILENCE_MINUTES * 60,
        int(PROACTIVE_SILENCE_MINUTES * 1.5) * 60,
    )
    job_queue.run_once(
        silence_callback,
        when=delay_seconds,
        data=chat_id,
        name=job_name,
    )


def register_jobs(app) -> None:
    """Register all proactive jobs on the application's JobQueue."""
    if not PROACTIVE_ENABLED:
        logger.info("Proactive features disabled (PROACTIVE_ENABLED=false)")
        return

    global session_manager
    from .handlers import session_manager as _sm
    session_manager = _sm
    _scheduler._session = session_manager

    job_queue = app.job_queue

    from .handlers import ALLOWED_CHAT_IDS

    # Daily date check at 09:00 local time
    job_queue.run_daily(
        check_dates_callback,
        time=datetime.now(PROACTIVE_TIMEZONE).replace(
            hour=9, minute=0, second=0
        ).timetz(),
        name="check_dates",
    )

    # Engagement jobs — 2 time windows per chat
    for chat_id in ALLOWED_CHAT_IDS:
        # Afternoon window: random time 12:00-15:00
        afternoon_hour = random.randint(12, 14)
        afternoon_min = random.randint(0, 59)
        job_queue.run_daily(
            engagement_callback,
            time=datetime.now(PROACTIVE_TIMEZONE).replace(
                hour=afternoon_hour, minute=afternoon_min, second=0
            ).timetz(),
            data=chat_id,
            name=f"engagement_afternoon_{chat_id}",
        )

        # Evening window: random time 18:00-21:00
        evening_hour = random.randint(18, 20)
        evening_min = random.randint(0, 59)
        job_queue.run_daily(
            engagement_callback,
            time=datetime.now(PROACTIVE_TIMEZONE).replace(
                hour=evening_hour, minute=evening_min, second=0
            ).timetz(),
            data=chat_id,
            name=f"engagement_evening_{chat_id}",
        )

    # Midnight reset of daily counters
    job_queue.run_daily(
        reset_daily_counts_callback,
        time=datetime.now(PROACTIVE_TIMEZONE).replace(
            hour=0, minute=0, second=0
        ).timetz(),
        name="reset_daily_counts",
    )

    logger.info(
        "Proactive scheduler registered: date checks at 09:00, "
        "engagement in afternoon+evening windows, silence breaker at %d min",
        PROACTIVE_SILENCE_MINUTES,
    )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scheduler.py -v`
Expected: All tests PASS.

**Step 5: Commit**

```bash
git add bot/scheduler.py tests/test_scheduler.py
git commit -m "feat: add ProactiveScheduler module with date, engagement, and silence jobs"
```

---

## Task 7: Wire Scheduler into Main and Handlers

**Files:**
- Modify: `bot/main.py` (lines 42-48)
- Modify: `bot/handlers.py` (line ~190, after message recording)
- Test: `tests/test_handlers.py`, `tests/test_scheduler.py`

**Step 1: Write failing test for silence timer reset**

Add to `tests/test_handlers.py`:

```python
@pytest.mark.asyncio
async def test_silence_timer_reset_called_on_message(mock_update, mock_context):
    """Each group message resets the silence timer."""
    mock_update.message.chat.type = "group"
    mock_update.message.chat_id = ALLOWED_CHAT_ID

    with (
        patch("bot.handlers.gemini_client"),
        patch("bot.handlers.user_memory") as mock_memory,
        patch("bot.handlers.session_manager"),
        patch("bot.handlers.reset_silence_timer") as mock_reset,
    ):
        mock_memory.increment_message_count.return_value = 1
        await handle_message(mock_update, mock_context)
        mock_reset.assert_called_once_with(mock_context.job_queue, ALLOWED_CHAT_ID)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_handlers.py -k "silence_timer" -v`
Expected: FAIL — `reset_silence_timer` not imported.

**Step 3: Modify `bot/handlers.py`**

Add import at top (after line 8):

```python
from .scheduler import reset_silence_timer
```

Add silence timer reset after message recording (after line 190, the `is_private` check):

```python
    # Reset silence breaker timer for this chat
    if hasattr(context, 'job_queue') and context.job_queue:
        reset_silence_timer(context.job_queue, chat_id)
```

Insert this right before line 191 (`is_private = ...`).

**Step 4: Modify `bot/main.py`**

Add import and registration. After line 16:

```python
from .scheduler import register_jobs
```

After line 45 (`app.add_handler(MessageHandler(...))`), add:

```python
    register_jobs(app)
```

**Step 5: Run tests**

Run: `pytest tests/test_handlers.py -k "silence_timer" -v`
Expected: PASS.

Run: `pytest -v`
Expected: All tests PASS.

**Step 6: Commit**

```bash
git add bot/main.py bot/handlers.py tests/test_handlers.py
git commit -m "feat: wire scheduler into main startup and message handler"
```

---

## Task 8: Configuration and Documentation

**Files:**
- Modify: `.env.example`
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `tests/conftest.py` (add `scheduled_events` cleanup)

**Step 1: Update `.env.example`**

Add after `MAX_HISTORY_MESSAGES=100`:

```
# Proactive bot features
PROACTIVE_ENABLED=false
PROACTIVE_TIMEZONE=Europe/Kyiv
PROACTIVE_DAILY_LIMIT=4
PROACTIVE_SILENCE_MINUTES=7
PROACTIVE_SILENCE_PROBABILITY=0.5
```

**Step 2: Update `AGENTS.md`**

Add a new section after "Chat Interaction Logic (Detailed)":

```markdown
## Proactive Messaging System

The bot can send messages on its own initiative via `bot/scheduler.py`:

- **Date congratulations**: Daily 09:00 check of `scheduled_events` table. Grouped by chat+event_type.
- **Engagement**: 1-2 times/day at random times. Gemini generates discussion starters or personal questions.
- **Silence breaker**: After 5-10 min of no messages, 50% chance the bot responds naturally.

Controlled by `PROACTIVE_ENABLED` env var (default: false). Jobs registered via `JobQueue` in `bot/main.py`.

Safety: daily limit per chat, night mode (23:00-08:00), date deduplication via `last_triggered`.

New files: `bot/scheduler.py`, `tests/test_scheduler.py`.
New table: `scheduled_events` (Alembic migration `a1b2c3d4e5f6`).
```

**Step 3: Update `README.md`**

Add to Features list:

```markdown
- **Proactive messaging** — congratulates on birthdays, starts discussions, and fills silence (configurable)
```

Add new env vars to Configuration table:

```markdown
| `PROACTIVE_ENABLED` | No | `false` | Enable proactive bot messages (date greetings, discussion starters, silence breaker) |
| `PROACTIVE_TIMEZONE` | No | `Europe/Kyiv` | Timezone for scheduling proactive messages |
| `PROACTIVE_DAILY_LIMIT` | No | `4` | Max proactive messages per chat per day |
| `PROACTIVE_SILENCE_MINUTES` | No | `7` | Minutes of silence before bot might respond |
| `PROACTIVE_SILENCE_PROBABILITY` | No | `0.5` | Probability (0-1) of responding to silence |
```

**Step 4: Update `tests/conftest.py`**

Add `scheduled_events` cleanup to both yield spots:

```python
conn.execute("DELETE FROM scheduled_events")
```

**Step 5: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS.

**Step 6: Commit**

```bash
git add .env.example AGENTS.md README.md tests/conftest.py
git commit -m "docs: add proactive features configuration and documentation"
```

---

## Task 9: Add `generate_congratulation`, `generate_engagement`, `generate_silence_response` to `_LazyGeminiClient`

**Files:**
- Modify: `bot/handlers.py` (add proxy methods to `_LazyGeminiClient`, lines ~80-92)

**Step 1: Add the proxy methods**

Add to `_LazyGeminiClient` class (after `extract_date_from_fact`):

```python
def generate_congratulation(
    self,
    event_type: str,
    persons: list[dict],
    person_facts: dict[str, list[str]],
) -> str:
    return self._get().generate_congratulation(
        event_type=event_type, persons=persons, person_facts=person_facts,
    )

def generate_engagement(
    self,
    members: list[dict],
    member_facts: dict[str, list[str]],
    recent_history: str,
) -> dict:
    return self._get().generate_engagement(
        members=members, member_facts=member_facts, recent_history=recent_history,
    )

def generate_silence_response(
    self,
    recent_messages: list[dict],
    author_facts: dict[str, list[str]],
) -> str:
    return self._get().generate_silence_response(
        recent_messages=recent_messages, author_facts=author_facts,
    )
```

**Step 2: Run full test suite**

Run: `pytest -v`
Expected: All tests PASS.

**Step 3: Commit**

```bash
git add bot/handlers.py
git commit -m "feat: add proactive generation methods to LazyGeminiClient proxy"
```

---

## Task 10: Integration Test — Full Proactive Flow

**Files:**
- Create: `tests/test_scheduler_integration.py`

**Step 1: Write integration test**

```python
"""Integration tests for the proactive scheduler using real DB."""
import sqlite3
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.memory import UserMemory


@pytest.fixture
def integration_memory(tmp_path):
    """Create a real UserMemory with migrated schema."""
    db = str(tmp_path / "test.db")
    from alembic.config import Config
    from alembic import command
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")
    return UserMemory(db_path=db)


def test_full_date_flow(integration_memory):
    """End-to-end: create user, upsert event, query by date, mark triggered."""
    mem = integration_memory
    # Create a user first
    mem.increment_message_count(user_id=1, chat_id=-100, username="olex", first_name="Oleksandr [ID: 1]")

    # Upsert a birthday event
    mem.upsert_scheduled_event(
        user_id=1, chat_id=-100, event_type="birthday",
        event_date="03-10", title="Oleksandr's birthday",
    )

    # Query today's events
    events = mem.get_events_for_date("03-10")
    assert len(events) == 1
    assert events[0]["title"] == "Oleksandr's birthday"
    assert events[0]["last_triggered"] is None

    # Mark triggered
    mem.mark_event_triggered(events[0]["id"])
    events_after = mem.get_events_for_date("03-10")
    assert events_after[0]["last_triggered"] is not None

    # Update same event (user birthday corrected)
    mem.upsert_scheduled_event(
        user_id=1, chat_id=-100, event_type="birthday",
        event_date="03-15", title="Oleksandr's birthday (corrected)",
    )
    old = mem.get_events_for_date("03-10")
    new = mem.get_events_for_date("03-15")
    assert len(old) == 0
    assert len(new) == 1
```

**Step 2: Run integration test**

Run: `pytest tests/test_scheduler_integration.py -v`
Expected: PASS.

**Step 3: Commit**

```bash
git add tests/test_scheduler_integration.py
git commit -m "test: add integration test for full proactive date flow"
```

---

## Task 11: Final Verification

**Step 1: Run full test suite**

Run: `pytest -v`
Expected: ALL tests PASS.

**Step 2: Verify no import errors**

Run: `python -c "from bot.scheduler import register_jobs, ProactiveScheduler; print('OK')"`
Expected: `OK`

**Step 3: Verify migration chain**

Run: `alembic history`
Expected: Shows `a1b2c3d4e5f6` as HEAD, chained from `b71d5f4a9c2e`.

**Step 4: Final commit with any remaining changes**

```bash
git status
# If anything is unstaged, commit it
```

---

## Summary of All Files Changed

| File | Action | Purpose |
|------|--------|---------|
| `alembic/versions/a1b2c3d4e5f6_add_scheduled_events.py` | Create | `scheduled_events` table migration |
| `bot/memory.py` | Modify | Add `upsert_scheduled_event`, `get_events_for_date`, `mark_event_triggered` |
| `bot/gemini.py` | Modify | Add `extract_date_from_fact`, `generate_congratulation`, `generate_engagement`, `generate_silence_response` |
| `bot/handlers.py` | Modify | Add lazy proxy methods, date extraction in `_update_user_profile`, silence timer reset |
| `bot/scheduler.py` | Create | `ProactiveScheduler` class, job callbacks, `register_jobs`, `reset_silence_timer` |
| `bot/main.py` | Modify | Import and call `register_jobs(app)` |
| `.env.example` | Modify | Add `PROACTIVE_*` variables |
| `AGENTS.md` | Modify | Document proactive system |
| `README.md` | Modify | Document new features and config |
| `tests/conftest.py` | Modify | Add `scheduled_events` cleanup |
| `tests/test_memory.py` | Modify | Add scheduled events tests |
| `tests/test_gemini.py` | Modify | Add proactive generation tests |
| `tests/test_handlers.py` | Modify | Add date extraction and silence timer tests |
| `tests/test_scheduler.py` | Create | Scheduler unit tests |
| `tests/test_scheduler_integration.py` | Create | Integration test for full flow |
