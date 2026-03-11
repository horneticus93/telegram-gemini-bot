# v2.0.0 LangGraph Bot Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite the Telegram bot as a LangGraph agent with global memory (no user_id in DB), chat summarization, and tool-based interactions.

**Architecture:** Hybrid LangGraph StateGraph where routing and summarization are graph-controlled, but the response generation step uses Gemini with tools (memory_search, memory_save, web_search). Memory is the bot's own — facts reference people by name in the text, not by FK.

**Tech Stack:** `langgraph>=1.0.0`, `langchain-google-genai>=4.0.0`, `python-telegram-bot>=21.0`, SQLite, Alembic.

---

### Task 1: Update dependencies

**Files:**
- Modify: `requirements.txt`

**Step 1: Update requirements.txt**

Replace contents with:

```
python-telegram-bot>=21.0,<22.0
langchain-google-genai>=4.0.0
langgraph>=1.0.0
python-dotenv>=1.0.0
alembic>=1.13.0
sqlalchemy>=2.0.0
```

**Step 2: Install dependencies**

Run: `pip install -r requirements.txt`
Expected: All packages install successfully.

**Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: update dependencies for v2 (langgraph + langchain-google-genai)"
```

---

### Task 2: Create config module

**Files:**
- Create: `bot/config.py`

**Step 1: Create bot/config.py**

```python
import os


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")

ALLOWED_CHAT_IDS: set[int] = {
    int(cid.strip())
    for cid in os.getenv("ALLOWED_CHAT_IDS", "").split(",")
    if cid.strip()
}

DB_PATH = os.getenv("DB_PATH", "/app/data/memory.db")
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "50"))

# Summarization triggers when this many messages accumulate since last summary
SUMMARY_THRESHOLD = 30
# Max words in running summary
SUMMARY_MAX_WORDS = 500
# Recent messages sent as full multi-turn history
RECENT_WINDOW_SIZE = 15
# Max tool call loops in agent node
MAX_AGENT_STEPS = 6
```

**Step 2: Commit**

```bash
git add bot/config.py
git commit -m "feat: add config module with all env vars and constants"
```

---

### Task 3: Create new memory module with tests (TDD)

**Files:**
- Create: `bot/memory.py` (new version)
- Create: `tests/test_memory.py` (new version)

**Step 1: Write failing tests for BotMemory**

Create `tests/test_memory.py`:

```python
import os
import tempfile

import pytest

from bot.memory import BotMemory


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def memory(db_path):
    mem = BotMemory(db_path=db_path)
    mem.init_db()
    return mem


def test_init_creates_table(memory):
    """memories table exists after init."""
    import sqlite3

    with sqlite3.connect(memory.db_path) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memories'"
        ).fetchall()
    assert len(tables) == 1


def test_save_and_search(memory):
    """Save a memory with embedding and retrieve it by similarity."""
    embedding = [1.0, 0.0, 0.0]
    memory.save_memory(
        content="Олександр любить піцу",
        embedding=embedding,
        importance=0.8,
        source="chat:-100123",
    )
    results = memory.search_memories(query_embedding=[1.0, 0.0, 0.0], limit=5)
    assert len(results) == 1
    assert results[0]["content"] == "Олександр любить піцу"


def test_search_respects_similarity(memory):
    """Only returns memories above similarity threshold."""
    memory.save_memory(content="fact A", embedding=[1.0, 0.0, 0.0], importance=0.5)
    memory.save_memory(content="fact B", embedding=[0.0, 1.0, 0.0], importance=0.5)
    results = memory.search_memories(
        query_embedding=[1.0, 0.0, 0.0], limit=5, min_similarity=0.5
    )
    assert len(results) == 1
    assert results[0]["content"] == "fact A"


def test_search_with_cooldown(memory):
    """Recently used memories are filtered by cooldown."""
    memory.save_memory(content="fact", embedding=[1.0, 0.0, 0.0], importance=0.5)
    results = memory.search_memories(query_embedding=[1.0, 0.0, 0.0], limit=5)
    assert len(results) == 1

    memory.mark_used([results[0]["id"]])
    results_after = memory.search_memories(
        query_embedding=[1.0, 0.0, 0.0], limit=5, cooldown_seconds=9999
    )
    assert len(results_after) == 0


def test_update_near_duplicate(memory):
    """Saving a near-duplicate updates the existing memory."""
    emb = [1.0, 0.0, 0.0]
    memory.save_memory(content="Олександр любить піцу", embedding=emb, importance=0.5)
    memory.save_or_update(
        content="Олександр обожнює піцу",
        embedding=emb,
        importance=0.7,
        source="chat:-100123",
        duplicate_threshold=0.85,
    )
    results = memory.search_memories(query_embedding=emb, limit=10)
    assert len(results) == 1
    assert results[0]["content"] == "Олександр обожнює піцу"
    assert results[0]["importance"] == 0.7


def test_save_or_update_adds_new_when_no_duplicate(memory):
    """Saving a non-duplicate creates a new memory."""
    memory.save_memory(content="fact A", embedding=[1.0, 0.0, 0.0], importance=0.5)
    memory.save_or_update(
        content="fact B",
        embedding=[0.0, 1.0, 0.0],
        importance=0.5,
        duplicate_threshold=0.85,
    )
    import sqlite3

    with sqlite3.connect(memory.db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    assert count == 2


def test_deactivate(memory):
    """Deactivated memories are not returned by search."""
    memory.save_memory(content="old fact", embedding=[1.0, 0.0, 0.0], importance=0.5)
    results = memory.search_memories(query_embedding=[1.0, 0.0, 0.0], limit=5)
    memory.deactivate(results[0]["id"])

    results_after = memory.search_memories(query_embedding=[1.0, 0.0, 0.0], limit=5)
    assert len(results_after) == 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_memory.py -v`
Expected: FAIL (ImportError — BotMemory doesn't exist yet)

**Step 3: Implement BotMemory**

Create `bot/memory.py`:

```python
import json
import math
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

RECENCY_DECAY_DAYS = 14.0
WEIGHT_SEMANTIC = 0.60
WEIGHT_RECENCY = 0.25
WEIGHT_IMPORTANCE = 0.15


class BotMemory:
    def __init__(self, db_path: str = "/app/data/memory.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    def init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    content      TEXT NOT NULL,
                    embedding    TEXT,
                    importance   REAL DEFAULT 0.5,
                    source       TEXT,
                    is_active    INTEGER DEFAULT 1,
                    use_count    INTEGER DEFAULT 0,
                    last_used_at TEXT,
                    created_at   TEXT NOT NULL,
                    updated_at   TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def save_memory(
        self,
        content: str,
        embedding: list[float] | None = None,
        importance: float = 0.5,
        source: str | None = None,
    ) -> int:
        now = _now_iso()
        emb_json = json.dumps(embedding) if embedding else None
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO memories (content, embedding, importance, source,
                                      is_active, use_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, 0, ?, ?)
                """,
                (content, emb_json, _clamp01(importance), source, now, now),
            )
            conn.commit()
            return cursor.lastrowid

    def search_memories(
        self,
        query_embedding: list[float],
        limit: int = 5,
        min_similarity: float = 0.2,
        cooldown_seconds: int = 900,
    ) -> list[dict]:
        if not query_embedding:
            return []
        now_dt = datetime.now(timezone.utc)
        results = []
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, content, embedding, importance, last_used_at, updated_at
                FROM memories
                WHERE is_active = 1 AND embedding IS NOT NULL
                """
            ).fetchall()
        for row in rows:
            mid, content, emb_str, importance, last_used_at, updated_at = row
            try:
                emb = json.loads(emb_str)
            except (json.JSONDecodeError, TypeError):
                continue
            sim = _cosine_similarity(emb, query_embedding)
            if sim is None or sim < min_similarity:
                continue
            if last_used_at and cooldown_seconds > 0:
                used_dt = _parse_ts(last_used_at)
                if (now_dt - used_dt).total_seconds() < cooldown_seconds:
                    continue
            updated_dt = _parse_ts(updated_at)
            age_days = max((now_dt - updated_dt).total_seconds() / 86400.0, 0.0)
            recency = math.exp(-age_days / RECENCY_DECAY_DAYS)
            imp = _clamp01(importance)
            score = (
                WEIGHT_SEMANTIC * sim
                + WEIGHT_RECENCY * recency
                + WEIGHT_IMPORTANCE * imp
            )
            results.append(
                {
                    "id": mid,
                    "content": content,
                    "importance": imp,
                    "score": score,
                }
            )
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def save_or_update(
        self,
        content: str,
        embedding: list[float],
        importance: float = 0.5,
        source: str | None = None,
        duplicate_threshold: float = 0.85,
    ) -> str:
        if not embedding:
            mid = self.save_memory(content, embedding, importance, source)
            return f"Saved new memory (id={mid})"
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, content, embedding
                FROM memories
                WHERE is_active = 1 AND embedding IS NOT NULL
                """
            ).fetchall()
        best_id = None
        best_sim = 0.0
        for row in rows:
            mid, _, emb_str = row
            try:
                emb = json.loads(emb_str)
            except (json.JSONDecodeError, TypeError):
                continue
            sim = _cosine_similarity(emb, embedding)
            if sim is not None and sim > best_sim:
                best_sim = sim
                best_id = mid
        if best_id is not None and best_sim >= duplicate_threshold:
            now = _now_iso()
            emb_json = json.dumps(embedding)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    UPDATE memories
                    SET content = ?, embedding = ?, importance = ?,
                        source = COALESCE(?, source), updated_at = ?
                    WHERE id = ?
                    """,
                    (content, emb_json, _clamp01(importance), source, now, best_id),
                )
                conn.commit()
            return f"Updated existing memory (id={best_id})"
        mid = self.save_memory(content, embedding, importance, source)
        return f"Saved new memory (id={mid})"

    def mark_used(self, memory_ids: list[int]) -> None:
        if not memory_ids:
            return
        placeholders = ",".join("?" for _ in memory_ids)
        now = _now_iso()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"""
                UPDATE memories
                SET use_count = use_count + 1, last_used_at = ?
                WHERE id IN ({placeholders})
                """,
                (now, *memory_ids),
            )
            conn.commit()

    def deactivate(self, memory_id: int) -> None:
        now = _now_iso()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE memories SET is_active = 0, updated_at = ? WHERE id = ?",
                (now, memory_id),
            )
            conn.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(ts: str | None) -> datetime:
    if not ts:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(ts)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return datetime.now(timezone.utc)


def _clamp01(value: float | int | None) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, parsed))


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float | None:
    if len(vec_a) != len(vec_b):
        return None
    mag_a = math.sqrt(sum(v * v for v in vec_a))
    mag_b = math.sqrt(sum(v * v for v in vec_b))
    if mag_a == 0 or mag_b == 0:
        return None
    return sum(a * b for a, b in zip(vec_a, vec_b)) / (mag_a * mag_b)
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_memory.py -v`
Expected: All 7 tests PASS.

**Step 5: Commit**

```bash
git add bot/memory.py tests/test_memory.py
git commit -m "feat: add BotMemory with global memory table and semantic search"
```

---

### Task 4: Create session module with summarization support (TDD)

**Files:**
- Create: `bot/session.py` (new version)
- Create: `tests/test_session.py` (new version)

**Step 1: Write failing tests**

Create `tests/test_session.py`:

```python
from bot.session import SessionManager


def test_add_and_get_history():
    sm = SessionManager(max_messages=10, recent_window=5)
    sm.add_message(1, "user", "hello", author="Alice")
    sm.add_message(1, "model", "hi there", author="bot")
    history = sm.get_history(1)
    assert len(history) == 2
    assert history[0]["text"] == "hello"


def test_get_recent_returns_window():
    sm = SessionManager(max_messages=20, recent_window=3)
    for i in range(10):
        sm.add_message(1, "user", f"msg {i}", author="Alice")
    recent = sm.get_recent(1)
    assert len(recent) == 3
    assert recent[0]["text"] == "msg 7"


def test_get_unsummarized_messages():
    sm = SessionManager(max_messages=20, recent_window=5)
    for i in range(10):
        sm.add_message(1, "user", f"msg {i}", author="Alice")
    unsummarized = sm.get_unsummarized(1)
    assert len(unsummarized) == 10

    sm.mark_summarized(1, count=10)
    unsummarized_after = sm.get_unsummarized(1)
    assert len(unsummarized_after) == 0


def test_summary_storage():
    sm = SessionManager(max_messages=20, recent_window=5)
    assert sm.get_summary(1) == ""
    sm.set_summary(1, "People discussed pizza.")
    assert sm.get_summary(1) == "People discussed pizza."


def test_format_history():
    sm = SessionManager(max_messages=10, recent_window=5)
    sm.add_message(1, "user", "hello", author="Alice")
    sm.add_message(1, "model", "hi", author="bot")
    formatted = sm.format_history(1)
    assert "[Alice]: hello" in formatted
    assert "[bot]: hi" in formatted


def test_needs_summary():
    sm = SessionManager(max_messages=50, recent_window=5)
    assert not sm.needs_summary(1, threshold=3)
    for i in range(5):
        sm.add_message(1, "user", f"msg {i}", author="Alice")
    assert sm.needs_summary(1, threshold=3)
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_session.py -v`
Expected: FAIL (ImportError)

**Step 3: Implement SessionManager**

Create `bot/session.py`:

```python
from collections import deque


class SessionManager:
    def __init__(self, max_messages: int = 50, recent_window: int = 15):
        self.max_messages = max_messages
        self.recent_window = recent_window
        self._sessions: dict[int, deque] = {}
        self._summaries: dict[int, str] = {}
        self._summarized_count: dict[int, int] = {}

    def add_message(
        self, chat_id: int, role: str, text: str, author: str | None = None
    ) -> None:
        if chat_id not in self._sessions:
            self._sessions[chat_id] = deque(maxlen=self.max_messages)
        self._sessions[chat_id].append(
            {"role": role, "text": text, "author": author}
        )

    def get_history(self, chat_id: int) -> list[dict]:
        if chat_id not in self._sessions:
            return []
        return list(self._sessions[chat_id])

    def get_recent(self, chat_id: int) -> list[dict]:
        history = self.get_history(chat_id)
        return history[-self.recent_window :]

    def get_unsummarized(self, chat_id: int) -> list[dict]:
        history = self.get_history(chat_id)
        offset = self._summarized_count.get(chat_id, 0)
        return history[offset:]

    def mark_summarized(self, chat_id: int, count: int) -> None:
        self._summarized_count[chat_id] = (
            self._summarized_count.get(chat_id, 0) + count
        )

    def get_summary(self, chat_id: int) -> str:
        return self._summaries.get(chat_id, "")

    def set_summary(self, chat_id: int, summary: str) -> None:
        self._summaries[chat_id] = summary

    def needs_summary(self, chat_id: int, threshold: int = 30) -> bool:
        return len(self.get_unsummarized(chat_id)) >= threshold

    def format_history(self, chat_id: int) -> str:
        entries = self.get_history(chat_id)
        return "\n".join(
            f"[{e['author'] or 'user'}]: {e['text']}"
            if e["role"] == "user"
            else f"[bot]: {e['text']}"
            for e in entries
        )
```

**Step 4: Run tests**

Run: `pytest tests/test_session.py -v`
Expected: All 6 tests PASS.

**Step 5: Commit**

```bash
git add bot/session.py tests/test_session.py
git commit -m "feat: add SessionManager with summarization tracking and recent window"
```

---

### Task 5: Create prompts module

**Files:**
- Create: `bot/prompts.py`

**Step 1: Create bot/prompts.py**

```python
SYSTEM_PROMPT = (
    "You are a member of a Telegram community. You're helpful, friendly, "
    "and speak naturally like a real person texting. You have your own memory.\n\n"
    "TOOLS:\n"
    "- Use memory_search to recall things you know about people, past events, "
    "or preferences. Search when you think you might know something relevant.\n"
    "- Use memory_save to remember important new facts for the future. "
    "Always include full context — who, where, what.\n"
    "  Good: \"Олександр в чаті 'Програмісти' працює в Google з 2023 року\"\n"
    "  Bad: \"працює в Google\" (missing who and where)\n"
    "- Use web_search to find current information (weather, news, prices, etc.).\n\n"
    "RULES:\n"
    "- Keep responses short (2-5 sentences). Be conversational, not formal.\n"
    "- Never say you'll look something up later — always answer now.\n"
    "- Use memory only when relevant. Don't force remembered facts into every reply.\n"
    "- When someone shares important personal info, save it to memory.\n"
    "- Respond in the same language as the user's message.\n"
)

SUMMARIZE_PROMPT = (
    "Summarize this conversation concisely. "
    "Focus on: key topics discussed, decisions made, important facts shared, "
    "and who said what (use names). "
    "Keep it under 200 words. Write as a third-person narrative summary."
)

SUMMARY_UPDATE_PROMPT = (
    "Here is the existing conversation summary:\n{existing_summary}\n\n"
    "Here are new messages since the last summary:\n{new_messages}\n\n"
    "Update the summary to include the new information. "
    "Keep the total under 500 words. Remove outdated details if needed. "
    "Write as a third-person narrative summary."
)
```

**Step 2: Commit**

```bash
git add bot/prompts.py
git commit -m "feat: add prompts module with system, summarize, and summary update prompts"
```

---

### Task 6: Create state module

**Files:**
- Create: `bot/state.py`

**Step 1: Create bot/state.py**

```python
from typing import Annotated, Any, Sequence, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class BotState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    chat_id: int
    user_name: str
    user_id: int
    bot_username: str
    question: str
    summary: str
    should_respond: bool
    response_text: str
    used_memory_ids: list[int]
```

**Step 2: Commit**

```bash
git add bot/state.py
git commit -m "feat: add BotState TypedDict for LangGraph state"
```

---

### Task 7: Create tools module (TDD)

**Files:**
- Create: `bot/tools.py`
- Create: `tests/test_tools.py`

**Step 1: Write failing tests**

Create `tests/test_tools.py`:

```python
import pytest
from unittest.mock import MagicMock, patch

from bot.tools import create_memory_search, create_memory_save


def test_memory_search_returns_results():
    mock_memory = MagicMock()
    mock_memory.search_memories.return_value = [
        {"id": 1, "content": "fact A", "score": 0.9},
        {"id": 2, "content": "fact B", "score": 0.7},
    ]
    mock_embed = MagicMock(return_value=[1.0, 0.0, 0.0])

    tool_fn = create_memory_search(mock_memory, mock_embed)
    result = tool_fn.invoke({"query": "test query"})
    assert "fact A" in result
    assert "fact B" in result
    mock_embed.assert_called_once_with("test query")


def test_memory_search_returns_nothing_found():
    mock_memory = MagicMock()
    mock_memory.search_memories.return_value = []
    mock_embed = MagicMock(return_value=[1.0, 0.0, 0.0])

    tool_fn = create_memory_search(mock_memory, mock_embed)
    result = tool_fn.invoke({"query": "unknown"})
    assert "nothing" in result.lower() or "no memories" in result.lower()


def test_memory_save_calls_save_or_update():
    mock_memory = MagicMock()
    mock_memory.save_or_update.return_value = "Saved new memory (id=1)"
    mock_embed = MagicMock(return_value=[1.0, 0.0, 0.0])

    tool_fn = create_memory_save(mock_memory, mock_embed)
    result = tool_fn.invoke({"memory": "Олександр любить піцу", "importance": 0.8})
    assert "Saved" in result or "saved" in result
    mock_memory.save_or_update.assert_called_once()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tools.py -v`
Expected: FAIL (ImportError)

**Step 3: Implement tools**

Create `bot/tools.py`:

```python
from typing import Callable

from langchain_core.tools import tool


def create_memory_search(
    memory, embed_fn: Callable[[str], list[float]]
):
    @tool
    def memory_search(query: str) -> str:
        """Search the bot's memory for relevant facts about people, events, or preferences. Use this when you think you might know something useful about the topic being discussed."""
        embedding = embed_fn(query)
        results = memory.search_memories(
            query_embedding=embedding, limit=5, cooldown_seconds=900
        )
        if not results:
            return "No memories found for this query."
        memory.mark_used([r["id"] for r in results])
        lines = [f"- {r['content']}" for r in results]
        return "Found memories:\n" + "\n".join(lines)

    return memory_search


def create_memory_save(
    memory, embed_fn: Callable[[str], list[float]]
):
    @tool
    def memory_save(memory_text: str, importance: float = 0.5) -> str:
        """Save an important fact to the bot's long-term memory. Always include full context: who, where, what. Example: 'Олександр в чаті Програмісти працює в Google з 2023 року'."""
        embedding = embed_fn(memory_text)
        result = memory.save_or_update(
            content=memory_text,
            embedding=embedding,
            importance=importance,
        )
        return result

    return memory_save


def create_web_search(llm):
    @tool
    def web_search(query: str) -> str:
        """Search the web for current information (weather, news, prices, events). Use this when you need up-to-date data that wouldn't be in your memory."""
        from langchain_core.messages import HumanMessage

        llm_with_search = llm.bind_tools([{"google_search": {}}])
        response = llm_with_search.invoke(
            [HumanMessage(content=f"Search the web and answer: {query}")]
        )
        return response.content or "No results found."

    return web_search
```

**Step 4: Run tests**

Run: `pytest tests/test_tools.py -v`
Expected: All 3 tests PASS.

**Step 5: Commit**

```bash
git add bot/tools.py tests/test_tools.py
git commit -m "feat: add tool factories for memory_search, memory_save, web_search"
```

---

### Task 8: Create graph module (TDD)

**Files:**
- Create: `bot/graph.py`
- Create: `tests/test_graph.py`

**Step 1: Write failing tests**

Create `tests/test_graph.py`:

```python
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from langchain_core.messages import HumanMessage, AIMessage

from bot.graph import build_graph, should_respond_node, build_context_node


def test_should_respond_private_chat():
    state = {
        "messages": [HumanMessage(content="hello")],
        "chat_id": 123,
        "user_name": "Alice",
        "user_id": 456,
        "bot_username": "testbot",
        "question": "hello",
        "summary": "",
        "should_respond": False,
        "response_text": "",
        "used_memory_ids": [],
    }
    # Private chat: chat_id > 0 (not a group)
    result = should_respond_node(state, is_private=True, is_reply_to_bot=False, is_mention=False)
    assert result["should_respond"] is True


def test_should_respond_group_mention():
    state = {
        "messages": [HumanMessage(content="@testbot hello")],
        "chat_id": -100123,
        "user_name": "Alice",
        "user_id": 456,
        "bot_username": "testbot",
        "question": "hello",
        "summary": "",
        "should_respond": False,
        "response_text": "",
        "used_memory_ids": [],
    }
    result = should_respond_node(state, is_private=False, is_reply_to_bot=False, is_mention=True)
    assert result["should_respond"] is True


def test_should_respond_group_no_mention():
    state = {
        "messages": [HumanMessage(content="hello everyone")],
        "chat_id": -100123,
        "user_name": "Alice",
        "user_id": 456,
        "bot_username": "testbot",
        "question": "hello everyone",
        "summary": "",
        "should_respond": False,
        "response_text": "",
        "used_memory_ids": [],
    }
    result = should_respond_node(state, is_private=False, is_reply_to_bot=False, is_mention=False)
    assert result["should_respond"] is False


def test_build_context_includes_summary():
    state = {
        "messages": [],
        "chat_id": 1,
        "user_name": "Alice",
        "user_id": 456,
        "bot_username": "testbot",
        "question": "what's up?",
        "summary": "Earlier, people discussed weekend plans.",
        "should_respond": True,
        "response_text": "",
        "used_memory_ids": [],
    }
    result = build_context_node(state, recent_messages=[
        {"role": "user", "text": "hey", "author": "Bob"},
    ])
    msgs = result["messages"]
    # Should have system-injected context about the summary
    combined = " ".join(m.content for m in msgs)
    assert "weekend plans" in combined


def test_build_graph_compiles():
    """Graph compiles without error."""
    mock_llm = MagicMock()
    mock_memory = MagicMock()
    mock_embed = MagicMock()
    graph = build_graph(mock_llm, mock_memory, mock_embed)
    assert graph is not None
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_graph.py -v`
Expected: FAIL (ImportError)

**Step 3: Implement graph**

Create `bot/graph.py`:

```python
import logging
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode, tools_condition

from .prompts import SYSTEM_PROMPT
from .state import BotState
from .tools import create_memory_save, create_memory_search, create_web_search

logger = logging.getLogger(__name__)


def should_respond_node(
    state: BotState,
    *,
    is_private: bool,
    is_reply_to_bot: bool,
    is_mention: bool,
) -> dict:
    should = is_private or is_reply_to_bot or is_mention
    return {"should_respond": should}


def build_context_node(
    state: BotState, *, recent_messages: list[dict]
) -> dict:
    context_parts = []
    summary = state.get("summary", "")
    if summary:
        context_parts.append(f"Conversation summary so far:\n{summary}")

    messages = []
    if context_parts:
        context_text = "\n\n".join(context_parts)
        messages.append(HumanMessage(content=context_text))
        messages.append(
            AIMessage(content="Got it, I have the context. What's the question?")
        )

    for entry in recent_messages:
        author = entry.get("author") or ("bot" if entry["role"] == "model" else "user")
        text = f"[{author}]: {entry['text']}"
        if entry["role"] == "user":
            messages.append(HumanMessage(content=text))
        else:
            messages.append(AIMessage(content=text))

    return {"messages": messages}


def _agent_node(state: BotState, llm_with_tools) -> dict:
    sys_msg = SystemMessage(content=SYSTEM_PROMPT)
    response = llm_with_tools.invoke([sys_msg] + list(state["messages"]))
    return {"messages": [response]}


def _route_after_respond_check(state: BotState) -> Literal["build_context", "__end__"]:
    if state.get("should_respond"):
        return "build_context"
    return END


def _route_after_agent(state: BotState) -> Literal["tools", "__end__"]:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END


def build_graph(llm, memory, embed_fn):
    tools = [
        create_memory_search(memory, embed_fn),
        create_memory_save(memory, embed_fn),
        create_web_search(llm),
    ]
    llm_with_tools = llm.bind_tools(tools)
    tool_node = ToolNode(tools)

    def agent_node(state: BotState):
        return _agent_node(state, llm_with_tools)

    graph = StateGraph(BotState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", _route_after_agent, {
        "tools": "tools",
        END: END,
    })
    graph.add_edge("tools", "agent")

    return graph.compile()
```

Note: The graph module exposes `should_respond_node` and `build_context_node` as standalone functions that `handlers.py` calls before invoking the graph. The compiled graph itself handles only the agent + tool loop. This keeps the graph simple and the handler logic testable.

**Step 4: Run tests**

Run: `pytest tests/test_graph.py -v`
Expected: All 5 tests PASS.

**Step 5: Commit**

```bash
git add bot/graph.py bot/state.py tests/test_graph.py
git commit -m "feat: add LangGraph StateGraph with agent + tool loop"
```

---

### Task 9: Create handlers module (TDD)

**Files:**
- Create: `bot/handlers.py` (new version)
- Create: `tests/test_handlers.py` (new version)

**Step 1: Write failing tests**

Create `tests/test_handlers.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from bot.handlers import handle_message


@pytest.fixture
def mock_update():
    update = MagicMock()
    update.message.text = "@testbot what is the weather?"
    update.message.chat_id = -100123
    update.message.chat.type = "group"
    update.message.from_user.id = 456
    update.message.from_user.first_name = "Alice"
    update.message.from_user.username = "alice"
    update.message.reply_to_message = None
    update.message.reply_text = AsyncMock()
    return update


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.bot.username = "testbot"
    ctx.bot.send_chat_action = AsyncMock()
    return ctx


@pytest.mark.asyncio
@patch("bot.handlers.ALLOWED_CHAT_IDS", {-100123})
@patch("bot.handlers.session_manager")
@patch("bot.handlers.bot_memory")
@patch("bot.handlers.compiled_graph")
@patch("bot.handlers.embed_text")
async def test_handle_message_responds_on_mention(
    mock_embed, mock_graph, mock_memory, mock_session, mock_update, mock_context
):
    mock_session.get_recent.return_value = []
    mock_session.get_summary.return_value = ""
    mock_session.needs_summary.return_value = False
    mock_embed.return_value = [1.0, 0.0]
    from langchain_core.messages import AIMessage
    mock_graph.invoke.return_value = {
        "messages": [AIMessage(content="It's sunny!")],
    }
    await handle_message(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_once_with("It's sunny!")


@pytest.mark.asyncio
@patch("bot.handlers.ALLOWED_CHAT_IDS", {-100123})
@patch("bot.handlers.session_manager")
async def test_handle_message_ignores_non_mention_in_group(
    mock_session, mock_update, mock_context
):
    mock_update.message.text = "hello everyone"
    await handle_message(mock_update, mock_context)
    mock_update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
@patch("bot.handlers.ALLOWED_CHAT_IDS", set())
@patch("bot.handlers.session_manager")
async def test_handle_message_ignores_disallowed_chat(
    mock_session, mock_update, mock_context
):
    await handle_message(mock_update, mock_context)
    mock_update.message.reply_text.assert_not_called()
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_handlers.py -v`
Expected: FAIL (ImportError)

**Step 3: Implement handlers**

Create `bot/handlers.py`:

```python
import asyncio
import logging

from langchain_core.messages import AIMessage, HumanMessage
from telegram import Update
from telegram.ext import ContextTypes

from .config import (
    ALLOWED_CHAT_IDS,
    DB_PATH,
    GEMINI_API_KEY,
    GEMINI_EMBEDDING_MODEL,
    GEMINI_MODEL,
    MAX_HISTORY_MESSAGES,
    RECENT_WINDOW_SIZE,
    SUMMARY_MAX_WORDS,
    SUMMARY_THRESHOLD,
)
from .graph import build_context_node, build_graph, should_respond_node
from .memory import BotMemory
from .session import SessionManager

logger = logging.getLogger(__name__)

session_manager = SessionManager(
    max_messages=MAX_HISTORY_MESSAGES,
    recent_window=RECENT_WINDOW_SIZE,
)
bot_memory = BotMemory(db_path=DB_PATH)


class _LazyGraph:
    """Lazy initialization so module can be imported without API key."""

    def __init__(self):
        self._graph = None
        self._llm = None
        self._embeddings = None

    def _init(self):
        from langchain_google_genai import (
            ChatGoogleGenerativeAI,
            GoogleGenerativeAIEmbeddings,
        )

        self._llm = ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            google_api_key=GEMINI_API_KEY,
            temperature=0.7,
            max_retries=2,
        )
        self._embeddings = GoogleGenerativeAIEmbeddings(
            model=GEMINI_EMBEDDING_MODEL,
            google_api_key=GEMINI_API_KEY,
        )
        self._graph = build_graph(
            self._llm, bot_memory, self._embeddings.embed_query
        )

    def invoke(self, state: dict) -> dict:
        if self._graph is None:
            self._init()
        return self._graph.invoke(state)

    def embed(self, text: str) -> list[float]:
        if self._embeddings is None:
            self._init()
        return self._embeddings.embed_query(text)


compiled_graph = _LazyGraph()


def embed_text(text: str) -> list[float]:
    return compiled_graph.embed(text)


async def handle_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not update.message or not update.message.text:
        return

    chat_id = update.message.chat_id
    if chat_id not in ALLOWED_CHAT_IDS:
        return

    user = update.message.from_user
    if user is None:
        return

    text = update.message.text
    author = f"{user.first_name or 'Unknown'} [ID: {user.id}]"
    bot_username = context.bot.username or "bot"

    session_manager.add_message(chat_id, "user", text, author=author)

    is_private = update.message.chat.type == "private"
    is_reply_to_bot = (
        update.message.reply_to_message is not None
        and update.message.reply_to_message.from_user is not None
        and update.message.reply_to_message.from_user.username == bot_username
    )
    is_mention = f"@{bot_username}" in text

    respond_result = should_respond_node(
        {},
        is_private=is_private,
        is_reply_to_bot=is_reply_to_bot,
        is_mention=is_mention,
    )
    if not respond_result["should_respond"]:
        return

    question = text.replace(f"@{bot_username}", "").strip() or text

    async def send_typing():
        while True:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(5)

    typing_task = asyncio.create_task(send_typing())

    try:
        recent = session_manager.get_recent(chat_id)
        summary = session_manager.get_summary(chat_id)

        context_result = build_context_node(
            {
                "messages": [],
                "chat_id": chat_id,
                "user_name": author,
                "user_id": user.id,
                "bot_username": bot_username,
                "question": question,
                "summary": summary,
                "should_respond": True,
                "response_text": "",
                "used_memory_ids": [],
            },
            recent_messages=recent,
        )

        messages = context_result["messages"]
        messages.append(HumanMessage(content=f"[{author}]: {question}"))

        graph_result = await asyncio.to_thread(
            compiled_graph.invoke,
            {
                "messages": messages,
                "chat_id": chat_id,
                "user_name": author,
                "user_id": user.id,
                "bot_username": bot_username,
                "question": question,
                "summary": summary,
                "should_respond": True,
                "response_text": "",
                "used_memory_ids": [],
            },
        )

        response_text = ""
        for msg in reversed(graph_result["messages"]):
            if isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                response_text = msg.content
                break

        typing_task.cancel()

        if not response_text:
            response_text = "Sorry, I couldn't generate a response."

        session_manager.add_message(chat_id, "model", response_text, author=bot_username)

        if len(response_text) <= 4096:
            await update.message.reply_text(response_text)
        else:
            for i in range(0, len(response_text), 4096):
                await update.message.reply_text(response_text[i : i + 4096])

        # Background summarization
        if session_manager.needs_summary(chat_id, threshold=SUMMARY_THRESHOLD):
            asyncio.create_task(
                _summarize_chat(chat_id)
            )

    except Exception:
        typing_task.cancel()
        logger.exception("Error processing message")
        await update.message.reply_text("Sorry, something went wrong. Try again.")


async def _summarize_chat(chat_id: int) -> None:
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage as HM

        from .config import GEMINI_API_KEY, GEMINI_MODEL
        from .prompts import SUMMARIZE_PROMPT, SUMMARY_UPDATE_PROMPT

        unsummarized = session_manager.get_unsummarized(chat_id)
        if not unsummarized:
            return

        new_msgs_text = "\n".join(
            f"[{e.get('author', 'user')}]: {e['text']}" for e in unsummarized
        )
        existing_summary = session_manager.get_summary(chat_id)

        if existing_summary:
            prompt = SUMMARY_UPDATE_PROMPT.format(
                existing_summary=existing_summary,
                new_messages=new_msgs_text,
            )
        else:
            prompt = f"{SUMMARIZE_PROMPT}\n\n{new_msgs_text}"

        llm = ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            google_api_key=GEMINI_API_KEY,
            temperature=0.3,
        )
        result = await asyncio.to_thread(
            llm.invoke, [HM(content=prompt)]
        )
        summary_text = result.content or ""

        words = summary_text.split()
        if len(words) > SUMMARY_MAX_WORDS:
            summary_text = " ".join(words[:SUMMARY_MAX_WORDS])

        session_manager.set_summary(chat_id, summary_text)
        session_manager.mark_summarized(chat_id, len(unsummarized))
        logger.info("Updated summary for chat %s", chat_id)
    except Exception:
        logger.exception("Failed to summarize chat %s", chat_id)
```

**Step 4: Run tests**

Run: `pytest tests/test_handlers.py -v`
Expected: All 3 tests PASS.

**Step 5: Commit**

```bash
git add bot/handlers.py tests/test_handlers.py
git commit -m "feat: add Telegram handlers with LangGraph integration and summarization"
```

---

### Task 10: Update main.py

**Files:**
- Modify: `bot/main.py`

**Step 1: Rewrite bot/main.py**

```python
import logging
import os

from dotenv import load_dotenv
from telegram.ext import Application, MessageHandler, filters

from .config import TELEGRAM_BOT_TOKEN, GEMINI_API_KEY
from .handlers import handle_message, bot_memory

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY environment variable is not set")

    bot_memory.init_db()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    logger.info("Bot v2.0.0 starting, polling for updates...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
```

**Step 2: Commit**

```bash
git add bot/main.py
git commit -m "feat: update main.py for v2 — init new DB and register handler"
```

---

### Task 11: Add Alembic migration for v2 schema

**Files:**
- Create: new Alembic revision

**Step 1: Generate migration**

Run: `cd /Users/oleksandr/Desktop/horneticus93/telegram-gemini-bot && alembic revision -m "v2 memories table"`

**Step 2: Edit the generated migration file**

The upgrade function should create the `memories` table:

```python
def upgrade():
    op.create_table(
        "memories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("importance", sa.Float(), server_default="0.5"),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Integer(), server_default="1"),
        sa.Column("use_count", sa.Integer(), server_default="0"),
        sa.Column("last_used_at", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )


def downgrade():
    op.drop_table("memories")
```

**Step 3: Commit**

```bash
git add alembic/versions/
git commit -m "feat: add Alembic migration for v2 memories table"
```

---

### Task 12: Update .env.example and AGENTS.md

**Files:**
- Modify: `.env.example`
- Modify: `AGENTS.md`

**Step 1: Update .env.example**

Remove `MEMORY_UPDATE_INTERVAL`. Update defaults:

```
TELEGRAM_BOT_TOKEN=your_token_here
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
ALLOWED_CHAT_IDS=-100123456789
MAX_HISTORY_MESSAGES=50
DB_PATH=/app/data/memory_v2.db
```

**Step 2: Update AGENTS.md**

Rewrite to reflect v2 architecture: LangGraph, new memory model, new module structure, new testing patterns. Remove references to `user_profiles`, `chat_memberships`, `memory_facts`, `/memory` command, `save_to_profile`, periodic profile updates.

**Step 3: Commit**

```bash
git add .env.example AGENTS.md
git commit -m "docs: update .env.example and AGENTS.md for v2 architecture"
```

---

### Task 13: Run full test suite and fix issues

**Step 1: Run all tests**

Run: `pytest -v`
Expected: All tests PASS.

**Step 2: Fix any failures**

If tests fail due to import issues from old modules being referenced, update the test files.

**Step 3: Final commit**

```bash
git add -A
git commit -m "fix: resolve test suite issues for v2"
```

---

### Task 14: Cleanup — remove unused old modules

**Files:**
- Remove: `bot/memory_handlers.py` (the /memory command UI)
- Keep but archive: old test files that reference v1 APIs

**Step 1: Remove memory_handlers.py**

```bash
git rm bot/memory_handlers.py
```

**Step 2: Remove old test files that test v1 code**

Evaluate which old tests in `tests/` reference removed v1 code (e.g., `test_memory.py` testing `UserMemory`, `test_handlers.py` testing old handler). Replace them entirely with the new test files from earlier tasks.

**Step 3: Commit**

```bash
git add -A
git commit -m "chore: remove v1 memory_handlers and old test files"
```

---

### Summary of commits

1. `chore: update dependencies for v2`
2. `feat: add config module`
3. `feat: add BotMemory with global memory table and semantic search`
4. `feat: add SessionManager with summarization tracking`
5. `feat: add prompts module`
6. `feat: add BotState TypedDict`
7. `feat: add tool factories for memory_search, memory_save, web_search`
8. `feat: add LangGraph StateGraph with agent + tool loop`
9. `feat: add Telegram handlers with LangGraph integration`
10. `feat: update main.py for v2`
11. `feat: add Alembic migration for v2 memories table`
12. `docs: update .env.example and AGENTS.md`
13. `fix: resolve test suite issues`
14. `chore: remove v1 modules`
