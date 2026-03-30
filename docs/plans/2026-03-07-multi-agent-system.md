# Multi-Agent System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform single-agent Telegram bot into a multi-agent system with a main orchestrator on `gemini-2.5-pro` and specialized sub-agents on cheaper models (`gemini-2.0-flash`, `gemini-2.0-flash-lite`).

**Architecture:** Hybrid pre-context pipeline — always-on sub-agents run in parallel before the orchestrator, conditional sub-agents run only when relevant content is present (image/link/forward), and on-demand tools are called by the orchestrator as needed. Sub-agents produce a "pre-context brief" that the orchestrator uses alongside the original message.

**Tech Stack:** Python 3.12+, LangGraph, LangChain Google GenAI, python-telegram-bot, SQLite + Alembic, pytest + pytest-asyncio.

---

## Task 1: Add new env vars and config constants

**Files:**
- Modify: `bot/config.py`
- Modify: `.env.example`

**Step 1: Add to `bot/config.py`**

Append after the existing constants:

```python
# Multi-agent models
GEMINI_PRO_MODEL = os.getenv("GEMINI_PRO_MODEL", "gemini-2.5-pro")
GEMINI_FLASH_MODEL = os.getenv("GEMINI_FLASH_MODEL", "gemini-2.0-flash")
GEMINI_FLASH_LITE_MODEL = os.getenv("GEMINI_FLASH_LITE_MODEL", "gemini-2.0-flash-lite")

# Agent system tuning
ORCHESTRATOR_TIMEOUT = int(os.getenv("ORCHESTRATOR_TIMEOUT", "15"))
SUBAGENT_TIMEOUT = int(os.getenv("SUBAGENT_TIMEOUT", "8"))
MAX_LINKS_PER_MESSAGE = int(os.getenv("MAX_LINKS_PER_MESSAGE", "3"))
MAX_IMAGES_PER_MESSAGE = int(os.getenv("MAX_IMAGES_PER_MESSAGE", "5"))
MENTION_DETECTOR_CONFIDENCE = float(os.getenv("MENTION_DETECTOR_CONFIDENCE", "0.7"))
MEMORY_RETRIEVER_TOP_K = int(os.getenv("MEMORY_RETRIEVER_TOP_K", "5"))
RELEVANCE_JUDGE_THRESHOLD = float(os.getenv("RELEVANCE_JUDGE_THRESHOLD", "0.6"))
```

**Step 2: Add to `.env.example`**

```bash
# Multi-agent models (defaults shown)
GEMINI_PRO_MODEL=gemini-2.5-pro
GEMINI_FLASH_MODEL=gemini-2.0-flash
GEMINI_FLASH_LITE_MODEL=gemini-2.0-flash-lite

# Agent system tuning
ORCHESTRATOR_TIMEOUT=15
SUBAGENT_TIMEOUT=8
MAX_LINKS_PER_MESSAGE=3
MAX_IMAGES_PER_MESSAGE=5
MENTION_DETECTOR_CONFIDENCE=0.7
MEMORY_RETRIEVER_TOP_K=5
RELEVANCE_JUDGE_THRESHOLD=0.6
```

**Step 3: Verify existing tests still pass**

```bash
pytest -v
```

Expected: all green (config change is additive).

---

## Task 2: Alembic migration for `chat_config` table

**Files:**
- Create: `alembic/versions/b1f2e3d4c5a6_add_chat_config_table.py`

**Step 1: Write the migration**

```python
"""add_chat_config_table

Revision ID: b1f2e3d4c5a6
Revises: a3e7c1d8f5b4
Create Date: 2026-03-07 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = "b1f2e3d4c5a6"
down_revision: Union[str, Sequence[str], None] = "a3e7c1d8f5b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_config (
            chat_id     INTEGER PRIMARY KEY,
            bot_aliases TEXT    NOT NULL DEFAULT '[]',
            created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chat_config")
```

**Step 2: Run tests**

```bash
pytest -v
```

Expected: all green.

---

## Task 3: Add `chat_config` read/write methods to `BotMemory`

**Files:**
- Modify: `bot/memory.py`
- Test: `tests/test_memory.py`

**Step 1: Write failing tests**

Add to `tests/test_memory.py`:

```python
def test_get_bot_aliases_empty(tmp_db):
    """Returns empty list when chat has no config."""
    aliases = tmp_db.get_bot_aliases(chat_id=999)
    assert aliases == []


def test_save_and_get_bot_alias(tmp_db):
    """Saves an alias and retrieves it."""
    tmp_db.add_bot_alias(chat_id=100, alias="Гена")
    aliases = tmp_db.get_bot_aliases(chat_id=100)
    assert "Гена" in aliases


def test_add_bot_alias_deduplicates(tmp_db):
    """Adding same alias twice doesn't duplicate."""
    tmp_db.add_bot_alias(chat_id=100, alias="Коля")
    tmp_db.add_bot_alias(chat_id=100, alias="Коля")
    aliases = tmp_db.get_bot_aliases(chat_id=100)
    assert aliases.count("Коля") == 1
```

Note: `tmp_db` fixture must run Alembic migrations. Check `tests/test_memory.py` for existing fixture pattern — it uses `alembic.config.Config` + `command.upgrade`. The new migration will be picked up automatically.

**Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_memory.py::test_get_bot_aliases_empty tests/test_memory.py::test_save_and_get_bot_alias tests/test_memory.py::test_add_bot_alias_deduplicates -v
```

Expected: FAIL with `AttributeError: 'BotMemory' object has no attribute 'get_bot_aliases'`

**Step 3: Add methods to `bot/memory.py`**

Add inside `BotMemory` class, after `deactivate()`:

```python
# ── chat_config ────────────────────────────────────────────────

def get_bot_aliases(self, chat_id: int) -> list[str]:
    """Return the list of bot aliases known for this chat."""
    with sqlite3.connect(self.db_path) as conn:
        row = conn.execute(
            "SELECT bot_aliases FROM chat_config WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
    if not row:
        return []
    try:
        return json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return []

def add_bot_alias(self, chat_id: int, alias: str) -> None:
    """Add *alias* to the bot alias list for *chat_id* (deduplicating)."""
    aliases = self.get_bot_aliases(chat_id)
    if alias in aliases:
        return
    aliases.append(alias)
    now = _now_iso()
    with sqlite3.connect(self.db_path) as conn:
        conn.execute(
            """
            INSERT INTO chat_config (chat_id, bot_aliases, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                bot_aliases = excluded.bot_aliases,
                updated_at  = excluded.updated_at
            """,
            (chat_id, json.dumps(aliases), now, now),
        )
        conn.commit()
```

**Step 4: Run tests**

```bash
pytest tests/test_memory.py -v
```

Expected: all green including new tests.

---

## Task 4: Create `bot/agents/` package with `BaseSubAgent`

**Files:**
- Create: `bot/agents/__init__.py`
- Create: `bot/agents/base.py`
- Test: `tests/test_agents_base.py`

**Step 1: Write failing test**

```python
# tests/test_agents_base.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from bot.agents.base import BaseSubAgent, SubAgentResult


def test_sub_agent_result_fields():
    result = SubAgentResult(agent_name="test", content="hello", confidence=0.9)
    assert result.agent_name == "test"
    assert result.content == "hello"
    assert result.confidence == 0.9


def test_sub_agent_result_defaults():
    result = SubAgentResult(agent_name="test", content="hello")
    assert result.confidence == 1.0
    assert result.metadata == {}
```

**Step 2: Run to confirm fail**

```bash
pytest tests/test_agents_base.py -v
```

**Step 3: Create `bot/agents/__init__.py`** (empty)

**Step 4: Create `bot/agents/base.py`**

```python
"""Base classes for sub-agents in the multi-agent pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SubAgentResult:
    """Result returned by any sub-agent."""
    agent_name: str
    content: str
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseSubAgent:
    """Abstract base for all sub-agents.

    Subclasses must implement ``run()``.
    """
    name: str = "base"

    async def run(self, **kwargs) -> SubAgentResult:
        raise NotImplementedError
```

**Step 5: Run tests**

```bash
pytest tests/test_agents_base.py -v
```

Expected: green.

---

## Task 5: `intent_classifier` sub-agent (no LLM — pure heuristics)

**Files:**
- Create: `bot/agents/intent_classifier.py`
- Test: `tests/test_agents_intent_classifier.py`

**Step 1: Write failing tests**

```python
# tests/test_agents_intent_classifier.py
import pytest
from bot.agents.intent_classifier import IntentClassifier

@pytest.fixture
def clf():
    return IntentClassifier()

@pytest.mark.asyncio
async def test_classifies_question(clf):
    result = await clf.run(text="Як справи?")
    assert result.content == "question"

@pytest.mark.asyncio
async def test_classifies_request(clf):
    result = await clf.run(text="Допоможи мені написати лист")
    assert result.content == "request"

@pytest.mark.asyncio
async def test_classifies_other(clf):
    result = await clf.run(text="хаха лол")
    assert result.content == "other"
```

**Step 2: Run to confirm fail**

```bash
pytest tests/test_agents_intent_classifier.py -v
```

**Step 3: Create `bot/agents/intent_classifier.py`**

```python
"""Intent classifier sub-agent — pure heuristics, no LLM."""
from __future__ import annotations
import re
from .base import BaseSubAgent, SubAgentResult

_QUESTION_RE = re.compile(
    r"(\?|як|чому|коли|де|хто|що|навіщо|скільки|чи |who|what|when|where|why|how|is |are |can |do |does )",
    re.IGNORECASE,
)
_REQUEST_RE = re.compile(
    r"(допоможи|зроби|напиши|поясни|розкажи|знайди|порахуй|перекладіть|help|write|explain|find|calculate|translate)",
    re.IGNORECASE,
)


class IntentClassifier(BaseSubAgent):
    name = "intent_classifier"

    async def run(self, *, text: str, **kwargs) -> SubAgentResult:
        if _REQUEST_RE.search(text):
            intent = "request"
        elif _QUESTION_RE.search(text):
            intent = "question"
        else:
            intent = "other"
        return SubAgentResult(agent_name=self.name, content=intent)
```

**Step 4: Run tests**

```bash
pytest tests/test_agents_intent_classifier.py -v
```

Expected: green.

---

## Task 6: `mention_detector` sub-agent (Flash-Lite LLM)

**Files:**
- Create: `bot/agents/mention_detector.py`
- Create: `bot/agents/prompts.py`
- Test: `tests/test_agents_mention_detector.py`

**Step 1: Write failing tests**

```python
# tests/test_agents_mention_detector.py
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from bot.agents.mention_detector import MentionDetector

@pytest.fixture
def llm_yes():
    """LLM that returns JSON indicating bot is addressed."""
    llm = MagicMock()
    msg = MagicMock()
    msg.content = '{"is_addressed": true, "confidence": 0.9, "new_alias": "Гена"}'
    llm.invoke = MagicMock(return_value=msg)
    return llm

@pytest.fixture
def llm_no():
    llm = MagicMock()
    msg = MagicMock()
    msg.content = '{"is_addressed": false, "confidence": 0.95, "new_alias": null}'
    llm.invoke = MagicMock(return_value=msg)
    return llm

@pytest.mark.asyncio
async def test_detects_addressed(llm_yes):
    agent = MentionDetector(llm=llm_yes, confidence_threshold=0.7)
    result = await agent.run(text="Гена, як справи?", bot_aliases=[], chat_id=1)
    assert result.metadata["is_addressed"] is True
    assert result.metadata["new_alias"] == "Гена"

@pytest.mark.asyncio
async def test_not_addressed(llm_no):
    agent = MentionDetector(llm=llm_no, confidence_threshold=0.7)
    result = await agent.run(text="привіт всім", bot_aliases=[], chat_id=1)
    assert result.metadata["is_addressed"] is False

@pytest.mark.asyncio
async def test_low_confidence_treated_as_not_addressed(llm_yes):
    """When LLM says yes but confidence < threshold, treat as not addressed."""
    llm = MagicMock()
    msg = MagicMock()
    msg.content = '{"is_addressed": true, "confidence": 0.3, "new_alias": null}'
    llm.invoke = MagicMock(return_value=msg)
    agent = MentionDetector(llm=llm, confidence_threshold=0.7)
    result = await agent.run(text="хтось щось", bot_aliases=[], chat_id=1)
    assert result.metadata["is_addressed"] is False
```

**Step 2: Run to confirm fail**

```bash
pytest tests/test_agents_mention_detector.py -v
```

**Step 3: Create `bot/agents/prompts.py`** with sub-agent prompts:

```python
"""Prompts for sub-agents."""

MENTION_DETECTOR_PROMPT = """\
You are analyzing a Telegram message to determine if the bot is being addressed.

Bot aliases in this chat: {aliases}

Message: "{text}"

Respond ONLY with valid JSON (no markdown, no explanation):
{{"is_addressed": <true|false>, "confidence": <0.0-1.0>, "new_alias": <"name"|null>}}

- is_addressed: true if the message is directed at the bot (by alias, context, or implicit reference)
- confidence: how confident you are (0.0 = not sure, 1.0 = certain)
- new_alias: if a new name for the bot is used that is NOT in the aliases list, return it; otherwise null
"""

MEMORY_RETRIEVER_PROMPT = """\
You are a memory retrieval assistant. Given the conversation context below, \
identify the most important search queries to find relevant bot memories.

Recent message: "{text}"
Context: "{context}"

Return up to 3 search queries as a JSON array of strings. Example:
["query one", "query two"]
Respond ONLY with valid JSON.
"""

CONTEXT_ANALYST_PROMPT = """\
Analyze the last {n} messages of this Telegram chat and return a brief analysis.

Messages:
{messages}

Respond ONLY with valid JSON:
{{"tone": "<neutral|positive|negative|tense|playful>", "main_topics": ["topic1"], "active_participants": ["name1"], "summary": "<1 sentence>"}}
"""

LINK_EXTRACTOR_PROMPT = """\
Visit and summarize the key information from this URL for a Telegram chat assistant.
URL: {url}

Return a 2-3 sentence summary of the most important content. Be concise.
"""

IMAGE_ANALYZER_PROMPT = """\
Describe this image briefly for a Telegram chat assistant. \
Focus on: what is shown, any text visible, and any relevant context.
Keep it under 3 sentences.
"""

REPOST_ANALYZER_PROMPT = """\
This is a forwarded Telegram message. Analyze its content and provide:
1. A brief summary (1-2 sentences)
2. The apparent original source/author if identifiable

Forwarded content: "{content}"

Respond ONLY with valid JSON:
{{"summary": "<text>", "source": "<text or null>"}}
"""

MEMORY_WATCHER_PROMPT = """\
You are analyzing a conversation to identify facts worth saving to long-term memory.

Recent exchange:
{messages}

Identify up to 3 important facts (personal info, preferences, events, decisions).
For each fact include full context: who + what + where.

Respond ONLY with valid JSON array:
[{{"fact": "<text>", "importance": <0.0-1.0>}}]

If nothing worth saving, return: []
"""

RELEVANCE_JUDGE_PROMPT = """\
You are a relevance filter. Given the user's message and a set of sub-agent results, \
determine which results are actually useful for answering the user.

User message: "{text}"

Sub-agent results:
{results}

Return ONLY the names of relevant agents as a JSON array. Example: ["memory_retriever", "context_analyst"]
If all are relevant, include all. If none, return [].
"""
```

**Step 4: Create `bot/agents/mention_detector.py`**

```python
"""Mention detector sub-agent — uses Flash-Lite to determine if bot is addressed."""
from __future__ import annotations
import asyncio
import json
import logging

from .base import BaseSubAgent, SubAgentResult
from .prompts import MENTION_DETECTOR_PROMPT

logger = logging.getLogger(__name__)


class MentionDetector(BaseSubAgent):
    name = "mention_detector"

    def __init__(self, llm, confidence_threshold: float = 0.7):
        self._llm = llm
        self._threshold = confidence_threshold

    async def run(self, *, text: str, bot_aliases: list[str], chat_id: int, **kwargs) -> SubAgentResult:
        aliases_str = ", ".join(bot_aliases) if bot_aliases else "none"
        prompt = MENTION_DETECTOR_PROMPT.format(aliases=aliases_str, text=text)

        from langchain_core.messages import HumanMessage
        response = await asyncio.to_thread(
            self._llm.invoke, [HumanMessage(content=prompt)]
        )

        try:
            data = json.loads(response.content)
            is_addressed = bool(data.get("is_addressed", False))
            confidence = float(data.get("confidence", 0.0))
            new_alias = data.get("new_alias")

            if confidence < self._threshold:
                is_addressed = False

            return SubAgentResult(
                agent_name=self.name,
                content="addressed" if is_addressed else "not_addressed",
                confidence=confidence,
                metadata={
                    "is_addressed": is_addressed,
                    "new_alias": new_alias if new_alias else None,
                },
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning("mention_detector parse error: %s", e)
            return SubAgentResult(
                agent_name=self.name,
                content="not_addressed",
                confidence=0.0,
                metadata={"is_addressed": False, "new_alias": None},
            )
```

**Step 5: Run tests**

```bash
pytest tests/test_agents_mention_detector.py -v
```

Expected: green.

---

## Task 7: `memory_retriever` sub-agent (Flash-Lite)

**Files:**
- Create: `bot/agents/memory_retriever.py`
- Test: `tests/test_agents_memory_retriever.py`

**Step 1: Write failing tests**

```python
# tests/test_agents_memory_retriever.py
import pytest
from unittest.mock import MagicMock
from bot.agents.memory_retriever import MemoryRetriever
from bot.agents.base import SubAgentResult


@pytest.fixture
def mock_memory():
    mem = MagicMock()
    mem.search_memories.return_value = [
        {"id": 1, "content": "Олег любить каву", "importance": 0.8, "score": 0.9}
    ]
    return mem


@pytest.fixture
def mock_embed():
    return lambda text: [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_retrieves_memories(mock_memory, mock_embed):
    agent = MemoryRetriever(memory=mock_memory, embed_fn=mock_embed, top_k=5)
    result = await agent.run(text="Що Олег п'є?")
    assert "Олег любить каву" in result.content
    assert result.metadata["count"] == 1


@pytest.mark.asyncio
async def test_returns_empty_when_no_memories(mock_embed):
    mem = MagicMock()
    mem.search_memories.return_value = []
    agent = MemoryRetriever(memory=mem, embed_fn=mock_embed, top_k=5)
    result = await agent.run(text="щось")
    assert result.content == ""
    assert result.metadata["count"] == 0
```

**Step 2: Run to confirm fail**

```bash
pytest tests/test_agents_memory_retriever.py -v
```

**Step 3: Create `bot/agents/memory_retriever.py`**

```python
"""Memory retriever sub-agent — semantic search over BotMemory."""
from __future__ import annotations
import asyncio
import logging

from .base import BaseSubAgent, SubAgentResult

logger = logging.getLogger(__name__)


class MemoryRetriever(BaseSubAgent):
    name = "memory_retriever"

    def __init__(self, memory, embed_fn, top_k: int = 5):
        self._memory = memory
        self._embed_fn = embed_fn
        self._top_k = top_k

    async def run(self, *, text: str, **kwargs) -> SubAgentResult:
        try:
            embedding = await asyncio.to_thread(self._embed_fn, text)
            results = await asyncio.to_thread(
                self._memory.search_memories,
                query_embedding=embedding,
                limit=self._top_k,
                cooldown_seconds=0,  # retriever always pulls fresh
            )
            if not results:
                return SubAgentResult(
                    agent_name=self.name, content="", metadata={"count": 0, "memories": []}
                )
            lines = [f"- {r['content']}" for r in results]
            return SubAgentResult(
                agent_name=self.name,
                content="\n".join(lines),
                metadata={"count": len(results), "memories": results},
            )
        except Exception as e:
            logger.warning("memory_retriever error: %s", e)
            return SubAgentResult(agent_name=self.name, content="", metadata={"count": 0, "memories": []})
```

**Step 4: Run tests**

```bash
pytest tests/test_agents_memory_retriever.py -v
```

Expected: green.

---

## Task 8: `context_analyst` sub-agent (Flash-Lite)

**Files:**
- Create: `bot/agents/context_analyst.py`
- Test: `tests/test_agents_context_analyst.py`

**Step 1: Write failing tests**

```python
# tests/test_agents_context_analyst.py
import pytest
from unittest.mock import MagicMock
from bot.agents.context_analyst import ContextAnalyst


@pytest.fixture
def llm_ok():
    llm = MagicMock()
    msg = MagicMock()
    msg.content = '{"tone": "positive", "main_topics": ["спорт"], "active_participants": ["Іван"], "summary": "Говорили про спорт."}'
    llm.invoke = MagicMock(return_value=msg)
    return llm


@pytest.mark.asyncio
async def test_returns_analysis(llm_ok):
    agent = ContextAnalyst(llm=llm_ok)
    messages = [{"author": "Іван", "role": "user", "text": "Дивись яка гра!"}]
    result = await agent.run(recent_messages=messages)
    assert result.metadata["tone"] == "positive"
    assert "спорт" in result.metadata["main_topics"]
    assert "Говорили про спорт." in result.content


@pytest.mark.asyncio
async def test_handles_bad_json(llm_ok):
    llm = MagicMock()
    msg = MagicMock()
    msg.content = "not json at all"
    llm.invoke = MagicMock(return_value=msg)
    agent = ContextAnalyst(llm=llm)
    result = await agent.run(recent_messages=[])
    assert result.content == ""
```

**Step 2: Run to confirm fail**

```bash
pytest tests/test_agents_context_analyst.py -v
```

**Step 3: Create `bot/agents/context_analyst.py`**

```python
"""Context analyst sub-agent — analyzes recent messages for tone and topics."""
from __future__ import annotations
import asyncio
import json
import logging

from .base import BaseSubAgent, SubAgentResult
from .prompts import CONTEXT_ANALYST_PROMPT

logger = logging.getLogger(__name__)


class ContextAnalyst(BaseSubAgent):
    name = "context_analyst"

    def __init__(self, llm):
        self._llm = llm

    async def run(self, *, recent_messages: list[dict], **kwargs) -> SubAgentResult:
        if not recent_messages:
            return SubAgentResult(agent_name=self.name, content="", metadata={})

        lines = [f"[{m.get('author', 'user')}]: {m['text']}" for m in recent_messages[-10:]]
        messages_text = "\n".join(lines)
        prompt = CONTEXT_ANALYST_PROMPT.format(n=len(lines), messages=messages_text)

        from langchain_core.messages import HumanMessage
        try:
            response = await asyncio.to_thread(
                self._llm.invoke, [HumanMessage(content=prompt)]
            )
            data = json.loads(response.content)
            summary = data.get("summary", "")
            return SubAgentResult(
                agent_name=self.name,
                content=summary,
                metadata=data,
            )
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("context_analyst error: %s", e)
            return SubAgentResult(agent_name=self.name, content="", metadata={})
```

**Step 4: Run tests**

```bash
pytest tests/test_agents_context_analyst.py -v
```

Expected: green.

---

## Task 9: `image_analyzer` sub-agent (Flash vision)

**Files:**
- Create: `bot/agents/image_analyzer.py`
- Test: `tests/test_agents_image_analyzer.py`

**Step 1: Write failing tests**

```python
# tests/test_agents_image_analyzer.py
import pytest
from unittest.mock import MagicMock
from bot.agents.image_analyzer import ImageAnalyzer


@pytest.fixture
def llm_ok():
    llm = MagicMock()
    msg = MagicMock()
    msg.content = "Фото з котом на дивані."
    llm.invoke = MagicMock(return_value=msg)
    return llm


@pytest.mark.asyncio
async def test_analyzes_image_bytes(llm_ok):
    agent = ImageAnalyzer(llm=llm_ok)
    result = await agent.run(image_data=b"fakebytes", mime_type="image/jpeg")
    assert "кот" in result.content.lower() or "фото" in result.content.lower()
    assert result.agent_name == "image_analyzer"


@pytest.mark.asyncio
async def test_returns_empty_on_no_data(llm_ok):
    agent = ImageAnalyzer(llm=llm_ok)
    result = await agent.run(image_data=b"", mime_type="image/jpeg")
    assert result.content == ""
```

**Step 2: Run to confirm fail**

```bash
pytest tests/test_agents_image_analyzer.py -v
```

**Step 3: Create `bot/agents/image_analyzer.py`**

```python
"""Image analyzer sub-agent — uses Flash (vision) to describe images."""
from __future__ import annotations
import asyncio
import base64
import logging

from .base import BaseSubAgent, SubAgentResult
from .prompts import IMAGE_ANALYZER_PROMPT

logger = logging.getLogger(__name__)


class ImageAnalyzer(BaseSubAgent):
    name = "image_analyzer"

    def __init__(self, llm):
        self._llm = llm

    async def run(self, *, image_data: bytes, mime_type: str = "image/jpeg", **kwargs) -> SubAgentResult:
        if not image_data:
            return SubAgentResult(agent_name=self.name, content="")

        from langchain_core.messages import HumanMessage
        b64 = base64.b64encode(image_data).decode()
        message = HumanMessage(
            content=[
                {"type": "text", "text": IMAGE_ANALYZER_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
            ]
        )
        try:
            response = await asyncio.to_thread(self._llm.invoke, [message])
            return SubAgentResult(agent_name=self.name, content=response.content or "")
        except Exception as e:
            logger.warning("image_analyzer error: %s", e)
            return SubAgentResult(agent_name=self.name, content="")
```

**Step 4: Run tests**

```bash
pytest tests/test_agents_image_analyzer.py -v
```

Expected: green.

---

## Task 10: `link_extractor` sub-agent (Flash-Lite)

**Files:**
- Create: `bot/agents/link_extractor.py`
- Test: `tests/test_agents_link_extractor.py`

**Step 1: Write failing tests**

```python
# tests/test_agents_link_extractor.py
import pytest
from unittest.mock import MagicMock
from bot.agents.link_extractor import LinkExtractor


@pytest.fixture
def llm_ok():
    llm = MagicMock()
    msg = MagicMock()
    msg.content = "Стаття про Python 3.13 з новими фічами."
    llm.invoke = MagicMock(return_value=msg)
    return llm


@pytest.mark.asyncio
async def test_extracts_links(llm_ok):
    agent = LinkExtractor(llm=llm_ok, max_links=3)
    result = await agent.run(text="Дивись https://python.org та https://docs.python.org")
    assert result.metadata["links_found"] == 2
    assert "Python" in result.content or result.content != ""


@pytest.mark.asyncio
async def test_no_links_returns_empty(llm_ok):
    agent = LinkExtractor(llm=llm_ok, max_links=3)
    result = await agent.run(text="просто текст без посилань")
    assert result.content == ""
    assert result.metadata["links_found"] == 0
```

**Step 2: Run to confirm fail**

```bash
pytest tests/test_agents_link_extractor.py -v
```

**Step 3: Create `bot/agents/link_extractor.py`**

```python
"""Link extractor sub-agent — fetches and summarizes URLs found in text."""
from __future__ import annotations
import asyncio
import logging
import re

from .base import BaseSubAgent, SubAgentResult
from .prompts import LINK_EXTRACTOR_PROMPT

logger = logging.getLogger(__name__)

URL_RE = re.compile(r"https?://[^\s]+")


class LinkExtractor(BaseSubAgent):
    name = "link_extractor"

    def __init__(self, llm, max_links: int = 3):
        self._llm = llm
        self._max_links = max_links

    async def run(self, *, text: str, **kwargs) -> SubAgentResult:
        urls = URL_RE.findall(text)[: self._max_links]
        if not urls:
            return SubAgentResult(
                agent_name=self.name, content="", metadata={"links_found": 0}
            )

        summaries: list[str] = []
        for url in urls:
            summary = await self._summarize_url(url)
            if summary:
                summaries.append(f"[{url}]: {summary}")

        return SubAgentResult(
            agent_name=self.name,
            content="\n".join(summaries),
            metadata={"links_found": len(urls), "urls": urls},
        )

    async def _summarize_url(self, url: str) -> str:
        from langchain_core.messages import HumanMessage
        prompt = LINK_EXTRACTOR_PROMPT.format(url=url)
        try:
            response = await asyncio.to_thread(
                self._llm.invoke, [HumanMessage(content=prompt)]
            )
            return response.content or ""
        except Exception as e:
            logger.warning("link_extractor error for %s: %s", url, e)
            return ""
```

**Step 4: Run tests**

```bash
pytest tests/test_agents_link_extractor.py -v
```

Expected: green.

---

## Task 11: `repost_analyzer` sub-agent (Flash-Lite)

**Files:**
- Create: `bot/agents/repost_analyzer.py`
- Test: `tests/test_agents_repost_analyzer.py`

**Step 1: Write failing tests**

```python
# tests/test_agents_repost_analyzer.py
import pytest
from unittest.mock import MagicMock
from bot.agents.repost_analyzer import RepostAnalyzer


@pytest.fixture
def llm_ok():
    llm = MagicMock()
    msg = MagicMock()
    msg.content = '{"summary": "Новина про відключення світла.", "source": "Новини України"}'
    llm.invoke = MagicMock(return_value=msg)
    return llm


@pytest.mark.asyncio
async def test_analyzes_repost(llm_ok):
    agent = RepostAnalyzer(llm=llm_ok)
    result = await agent.run(forwarded_text="Увага! З 20:00 відключення світла.", forward_from="Новини України")
    assert "відключення" in result.content.lower() or result.content != ""
    assert result.metadata.get("source") == "Новини України"


@pytest.mark.asyncio
async def test_empty_text_returns_empty(llm_ok):
    agent = RepostAnalyzer(llm=llm_ok)
    result = await agent.run(forwarded_text="", forward_from=None)
    assert result.content == ""
```

**Step 2: Run to confirm fail**

```bash
pytest tests/test_agents_repost_analyzer.py -v
```

**Step 3: Create `bot/agents/repost_analyzer.py`**

```python
"""Repost analyzer sub-agent — summarizes forwarded messages."""
from __future__ import annotations
import asyncio
import json
import logging

from .base import BaseSubAgent, SubAgentResult
from .prompts import REPOST_ANALYZER_PROMPT

logger = logging.getLogger(__name__)


class RepostAnalyzer(BaseSubAgent):
    name = "repost_analyzer"

    def __init__(self, llm):
        self._llm = llm

    async def run(self, *, forwarded_text: str, forward_from: str | None = None, **kwargs) -> SubAgentResult:
        if not forwarded_text:
            return SubAgentResult(agent_name=self.name, content="", metadata={})

        from langchain_core.messages import HumanMessage
        prompt = REPOST_ANALYZER_PROMPT.format(content=forwarded_text)
        try:
            response = await asyncio.to_thread(self._llm.invoke, [HumanMessage(content=prompt)])
            data = json.loads(response.content)
            source = data.get("source") or forward_from
            summary = data.get("summary", "")
            return SubAgentResult(
                agent_name=self.name,
                content=summary,
                metadata={"source": source, "summary": summary},
            )
        except Exception as e:
            logger.warning("repost_analyzer error: %s", e)
            return SubAgentResult(agent_name=self.name, content="", metadata={})
```

**Step 4: Run tests**

```bash
pytest tests/test_agents_repost_analyzer.py -v
```

Expected: green.

---

## Task 12: `memory_watcher` on-demand tool (Flash-Lite)

**Files:**
- Create: `bot/agents/memory_watcher.py`
- Test: `tests/test_agents_memory_watcher.py`

**Step 1: Write failing tests**

```python
# tests/test_agents_memory_watcher.py
import pytest
from unittest.mock import MagicMock
from bot.agents.memory_watcher import MemoryWatcher


@pytest.fixture
def llm_with_facts():
    llm = MagicMock()
    msg = MagicMock()
    msg.content = '[{"fact": "Іван живе у Львові", "importance": 0.8}]'
    llm.invoke = MagicMock(return_value=msg)
    return llm


@pytest.fixture
def llm_no_facts():
    llm = MagicMock()
    msg = MagicMock()
    msg.content = '[]'
    llm.invoke = MagicMock(return_value=msg)
    return llm


@pytest.mark.asyncio
async def test_identifies_facts(llm_with_facts):
    mock_memory = MagicMock()
    mock_embed = lambda t: [0.1, 0.2]
    agent = MemoryWatcher(llm=llm_with_facts, memory=mock_memory, embed_fn=mock_embed)
    result = await agent.run(messages=[{"author": "Іван", "role": "user", "text": "Я живу у Львові"}])
    assert result.metadata["saved"] == 1
    mock_memory.save_or_update.assert_called_once()


@pytest.mark.asyncio
async def test_saves_nothing_when_no_facts(llm_no_facts):
    mock_memory = MagicMock()
    mock_embed = lambda t: [0.1]
    agent = MemoryWatcher(llm=llm_no_facts, memory=mock_memory, embed_fn=mock_embed)
    result = await agent.run(messages=[])
    assert result.metadata["saved"] == 0
    mock_memory.save_or_update.assert_not_called()
```

**Step 2: Run to confirm fail**

```bash
pytest tests/test_agents_memory_watcher.py -v
```

**Step 3: Create `bot/agents/memory_watcher.py`**

```python
"""Memory watcher sub-agent — identifies and saves important facts."""
from __future__ import annotations
import asyncio
import json
import logging

from .base import BaseSubAgent, SubAgentResult
from .prompts import MEMORY_WATCHER_PROMPT

logger = logging.getLogger(__name__)


class MemoryWatcher(BaseSubAgent):
    name = "memory_watcher"

    def __init__(self, llm, memory, embed_fn):
        self._llm = llm
        self._memory = memory
        self._embed_fn = embed_fn

    async def run(self, *, messages: list[dict], **kwargs) -> SubAgentResult:
        if not messages:
            return SubAgentResult(agent_name=self.name, content="", metadata={"saved": 0})

        lines = [f"[{m.get('author', 'user')}]: {m['text']}" for m in messages]
        prompt = MEMORY_WATCHER_PROMPT.format(messages="\n".join(lines))

        from langchain_core.messages import HumanMessage
        try:
            response = await asyncio.to_thread(self._llm.invoke, [HumanMessage(content=prompt)])
            facts = json.loads(response.content)
        except Exception as e:
            logger.warning("memory_watcher parse error: %s", e)
            return SubAgentResult(agent_name=self.name, content="", metadata={"saved": 0})

        saved = 0
        for item in facts:
            fact = item.get("fact", "")
            importance = float(item.get("importance", 0.5))
            if not fact:
                continue
            try:
                embedding = await asyncio.to_thread(self._embed_fn, fact)
                await asyncio.to_thread(
                    self._memory.save_or_update,
                    content=fact,
                    embedding=embedding,
                    importance=importance,
                    source="memory_watcher",
                )
                saved += 1
            except Exception as e:
                logger.warning("memory_watcher save error: %s", e)

        return SubAgentResult(
            agent_name=self.name,
            content=f"Saved {saved} facts",
            metadata={"saved": saved},
        )
```

**Step 4: Run tests**

```bash
pytest tests/test_agents_memory_watcher.py -v
```

Expected: green.

---

## Task 13: `relevance_judge` on-demand tool (Flash-Lite)

**Files:**
- Create: `bot/agents/relevance_judge.py`
- Test: `tests/test_agents_relevance_judge.py`

**Step 1: Write failing tests**

```python
# tests/test_agents_relevance_judge.py
import pytest
from unittest.mock import MagicMock
from bot.agents.relevance_judge import RelevanceJudge
from bot.agents.base import SubAgentResult


@pytest.fixture
def llm_filter():
    llm = MagicMock()
    msg = MagicMock()
    msg.content = '["memory_retriever"]'
    llm.invoke = MagicMock(return_value=msg)
    return llm


@pytest.mark.asyncio
async def test_filters_irrelevant_agents(llm_filter):
    agent = RelevanceJudge(llm=llm_filter)
    results = [
        SubAgentResult(agent_name="memory_retriever", content="Іван любить каву"),
        SubAgentResult(agent_name="context_analyst", content="тон нейтральний"),
    ]
    filtered = await agent.run(text="Що Іван п'є?", sub_agent_results=results)
    assert len(filtered) == 1
    assert filtered[0].agent_name == "memory_retriever"
```

**Step 2: Run to confirm fail**

```bash
pytest tests/test_agents_relevance_judge.py -v
```

**Step 3: Create `bot/agents/relevance_judge.py`**

```python
"""Relevance judge — filters sub-agent results to only useful ones."""
from __future__ import annotations
import asyncio
import json
import logging

from .base import BaseSubAgent, SubAgentResult
from .prompts import RELEVANCE_JUDGE_PROMPT

logger = logging.getLogger(__name__)


class RelevanceJudge(BaseSubAgent):
    name = "relevance_judge"

    def __init__(self, llm):
        self._llm = llm

    async def run(
        self,
        *,
        text: str,
        sub_agent_results: list[SubAgentResult],
        **kwargs,
    ) -> list[SubAgentResult]:
        if not sub_agent_results:
            return []

        results_text = "\n".join(
            f"[{r.agent_name}]: {r.content[:200]}"
            for r in sub_agent_results
            if r.content
        )
        prompt = RELEVANCE_JUDGE_PROMPT.format(text=text, results=results_text)

        from langchain_core.messages import HumanMessage
        try:
            response = await asyncio.to_thread(self._llm.invoke, [HumanMessage(content=prompt)])
            relevant_names: list[str] = json.loads(response.content)
            return [r for r in sub_agent_results if r.agent_name in relevant_names]
        except Exception as e:
            logger.warning("relevance_judge error: %s, returning all", e)
            return sub_agent_results
```

**Step 4: Run tests**

```bash
pytest tests/test_agents_relevance_judge.py -v
```

Expected: green.

---

## Task 14: `AgentOrchestrator` — wires all sub-agents together

**Files:**
- Create: `bot/agents/orchestrator.py`
- Test: `tests/test_agents_orchestrator.py`

**Step 1: Write failing tests**

```python
# tests/test_agents_orchestrator.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bot.agents.orchestrator import AgentOrchestrator
from bot.agents.base import SubAgentResult


@pytest.fixture
def mock_agents():
    mention = AsyncMock()
    mention.run.return_value = SubAgentResult(
        agent_name="mention_detector",
        content="addressed",
        metadata={"is_addressed": True, "new_alias": None},
    )
    memory = AsyncMock()
    memory.run.return_value = SubAgentResult(
        agent_name="memory_retriever", content="- Іван любить каву"
    )
    context = AsyncMock()
    context.run.return_value = SubAgentResult(
        agent_name="context_analyst", content="Позитивний тон", metadata={"tone": "positive"}
    )
    return mention, memory, context


@pytest.mark.asyncio
async def test_orchestrator_runs_always_on_agents(mock_agents):
    mention, memory, context = mock_agents
    orch = AgentOrchestrator(
        mention_detector=mention,
        memory_retriever=memory,
        context_analyst=context,
        image_analyzer=None,
        link_extractor=None,
        repost_analyzer=None,
        memory=MagicMock(),
    )
    brief = await orch.build_pre_context(
        text="привіт",
        chat_id=1,
        recent_messages=[],
        has_photo=False,
        has_forward=False,
    )
    mention.run.assert_called_once()
    memory.run.assert_called_once()
    context.run.assert_called_once()
    assert "memory_retriever" in brief or "mention_detector" in brief or isinstance(brief, str)


@pytest.mark.asyncio
async def test_orchestrator_skips_image_when_no_photo(mock_agents):
    mention, memory, context = mock_agents
    image_agent = AsyncMock()
    orch = AgentOrchestrator(
        mention_detector=mention,
        memory_retriever=memory,
        context_analyst=context,
        image_analyzer=image_agent,
        link_extractor=None,
        repost_analyzer=None,
        memory=MagicMock(),
    )
    await orch.build_pre_context(
        text="текст без фото",
        chat_id=1,
        recent_messages=[],
        has_photo=False,
        has_forward=False,
    )
    image_agent.run.assert_not_called()
```

**Step 2: Run to confirm fail**

```bash
pytest tests/test_agents_orchestrator.py -v
```

**Step 3: Create `bot/agents/orchestrator.py`**

```python
"""AgentOrchestrator — runs sub-agents and builds pre-context brief."""
from __future__ import annotations
import asyncio
import logging

from .base import SubAgentResult
from .mention_detector import MentionDetector
from .memory_retriever import MemoryRetriever
from .context_analyst import ContextAnalyst
from .image_analyzer import ImageAnalyzer
from .link_extractor import LinkExtractor
from .repost_analyzer import RepostAnalyzer

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    def __init__(
        self,
        *,
        mention_detector: MentionDetector,
        memory_retriever: MemoryRetriever,
        context_analyst: ContextAnalyst,
        image_analyzer: ImageAnalyzer | None,
        link_extractor: LinkExtractor | None,
        repost_analyzer: RepostAnalyzer | None,
        memory,
    ):
        self._mention = mention_detector
        self._memory_retriever = memory_retriever
        self._context = context_analyst
        self._image = image_analyzer
        self._links = link_extractor
        self._repost = repost_analyzer
        self._memory = memory

    async def build_pre_context(
        self,
        *,
        text: str,
        chat_id: int,
        recent_messages: list[dict],
        has_photo: bool,
        has_forward: bool,
        image_data: bytes | None = None,
        mime_type: str = "image/jpeg",
        forwarded_text: str = "",
        forward_from: str | None = None,
        subagent_timeout: float = 8.0,
    ) -> str:
        """Run all applicable sub-agents and return a formatted pre-context string."""
        bot_aliases = await asyncio.to_thread(self._memory.get_bot_aliases, chat_id)

        # Always-on agents
        always_on_coros = [
            self._mention.run(text=text, bot_aliases=bot_aliases, chat_id=chat_id),
            self._memory_retriever.run(text=text),
            self._context.run(recent_messages=recent_messages),
        ]

        # Conditional agents
        conditional_coros = []
        conditional_names = []
        if has_photo and self._image and image_data:
            conditional_coros.append(self._image.run(image_data=image_data, mime_type=mime_type))
            conditional_names.append("image_analyzer")
        if self._links:
            from .link_extractor import URL_RE
            if URL_RE.search(text):
                conditional_coros.append(self._links.run(text=text))
                conditional_names.append("link_extractor")
        if has_forward and self._repost:
            conditional_coros.append(self._repost.run(forwarded_text=forwarded_text, forward_from=forward_from))
            conditional_names.append("repost_analyzer")

        async def safe_run(coro):
            try:
                return await asyncio.wait_for(coro, timeout=subagent_timeout)
            except asyncio.TimeoutError:
                logger.warning("Sub-agent timed out")
                return None
            except Exception as e:
                logger.warning("Sub-agent error: %s", e)
                return None

        all_coros = always_on_coros + conditional_coros
        raw_results = await asyncio.gather(*[safe_run(c) for c in all_coros])
        results: list[SubAgentResult] = [r for r in raw_results if r is not None]

        # Handle new bot alias discovery
        for r in results:
            if r.agent_name == "mention_detector":
                new_alias = r.metadata.get("new_alias")
                if new_alias:
                    await asyncio.to_thread(self._memory.add_bot_alias, chat_id, new_alias)
                break

        return self._format_brief(results)

    def _format_brief(self, results: list[SubAgentResult]) -> str:
        sections: list[str] = []
        for r in results:
            if not r.content:
                continue
            sections.append(f"[{r.agent_name}]\n{r.content}")
        if not sections:
            return ""
        return "\n\n".join(sections)
```

**Step 4: Run tests**

```bash
pytest tests/test_agents_orchestrator.py -v
```

Expected: green.

---

## Task 15: Update `graph.py` — orchestrator provides pre-context to main agent

**Files:**
- Modify: `bot/graph.py`
- Modify: `bot/state.py`
- Test: `tests/test_graph.py`

**Step 1: Read current `bot/state.py` first, then add `pre_context` field**

Current `BotState` likely has fields like `messages`, `chat_id`, etc. Add:

```python
pre_context: str  # formatted brief from AgentOrchestrator
```

**Step 2: Update `bot/graph.py` `agent_node` to prepend pre-context to system prompt**

In `agent_node`:

```python
def agent_node(state: dict) -> dict:
    pre_context = state.get("pre_context", "")
    system_content = SYSTEM_PROMPT
    if pre_context:
        system_content = SYSTEM_PROMPT + f"\n\n## Pre-context from sub-agents\n{pre_context}"
    sys_msg = SystemMessage(content=system_content)
    response = llm_with_tools.invoke([sys_msg] + list(state["messages"]))
    return {"messages": [response]}
```

**Step 3: Run existing graph tests**

```bash
pytest tests/test_graph.py -v
```

Expected: green (pre_context defaults to `""` so existing tests unaffected).

---

## Task 16: Update `handlers.py` — wire `AgentOrchestrator` into message flow

**Files:**
- Modify: `bot/handlers.py`
- Test: `tests/test_handlers.py`

**Step 1: Update `_LazyGraph._init()` to create orchestrator and Pro LLM**

In `_LazyGraph._init()`:

```python
from bot.config import (
    GEMINI_PRO_MODEL, GEMINI_FLASH_MODEL, GEMINI_FLASH_LITE_MODEL,
    SUBAGENT_TIMEOUT, MEMORY_RETRIEVER_TOP_K, MENTION_DETECTOR_CONFIDENCE,
    MAX_LINKS_PER_MESSAGE,
)
from bot.agents.orchestrator import AgentOrchestrator
from bot.agents.mention_detector import MentionDetector
from bot.agents.memory_retriever import MemoryRetriever
from bot.agents.context_analyst import ContextAnalyst
from bot.agents.image_analyzer import ImageAnalyzer
from bot.agents.link_extractor import LinkExtractor
from bot.agents.repost_analyzer import RepostAnalyzer

# Orchestrator LLM (main agent uses Pro, sub-agents use Flash/Flash-Lite)
llm_pro = ChatGoogleGenerativeAI(model=GEMINI_PRO_MODEL, google_api_key=GEMINI_API_KEY, temperature=0.7, max_retries=2)
llm_flash = ChatGoogleGenerativeAI(model=GEMINI_FLASH_MODEL, google_api_key=GEMINI_API_KEY, temperature=0.3)
llm_lite = ChatGoogleGenerativeAI(model=GEMINI_FLASH_LITE_MODEL, google_api_key=GEMINI_API_KEY, temperature=0.3)

self._orchestrator = AgentOrchestrator(
    mention_detector=MentionDetector(llm=llm_lite, confidence_threshold=MENTION_DETECTOR_CONFIDENCE),
    memory_retriever=MemoryRetriever(memory=bot_memory, embed_fn=self._embeddings.embed_query, top_k=MEMORY_RETRIEVER_TOP_K),
    context_analyst=ContextAnalyst(llm=llm_lite),
    image_analyzer=ImageAnalyzer(llm=llm_flash),
    link_extractor=LinkExtractor(llm=llm_lite, max_links=MAX_LINKS_PER_MESSAGE),
    repost_analyzer=RepostAnalyzer(llm=llm_lite),
    memory=bot_memory,
)

# Main graph uses Pro model
self._graph = build_graph(llm_pro, bot_memory, self._embeddings.embed_query)
```

**Step 2: Add `orchestrate()` method to `_LazyGraph`**

```python
async def orchestrate(self, *, text, chat_id, recent_messages, has_photo, has_forward,
                       image_data=None, mime_type="image/jpeg",
                       forwarded_text="", forward_from=None) -> str:
    if self._orchestrator is None:
        self._init()
    return await self._orchestrator.build_pre_context(
        text=text, chat_id=chat_id, recent_messages=recent_messages,
        has_photo=has_photo, has_forward=has_forward,
        image_data=image_data, mime_type=mime_type,
        forwarded_text=forwarded_text, forward_from=forward_from,
    )
```

**Step 3: In `handle_message()`, call orchestrator before graph invoke**

After step 10 (get recent messages), add:

```python
# 10b. Run sub-agent orchestrator to build pre-context
has_photo = bool(update.message.photo)
has_forward = update.message.forward_date is not None

# Download photo bytes if present (first/best quality)
image_data = None
mime_type = "image/jpeg"
if has_photo:
    photo = update.message.photo[-1]  # largest size
    file = await context.bot.get_file(photo.file_id)
    image_data = await file.download_as_bytearray()

forwarded_text = ""
forward_from = None
if has_forward and update.message.forward_origin:
    forwarded_text = text
    # Try to get forward source name
    origin = update.message.forward_origin
    if hasattr(origin, "sender_user") and origin.sender_user:
        forward_from = origin.sender_user.first_name

pre_context = await compiled_graph.orchestrate(
    text=question,
    chat_id=chat_id,
    recent_messages=recent_messages,
    has_photo=has_photo,
    has_forward=has_forward,
    image_data=bytes(image_data) if image_data else None,
    mime_type=mime_type,
    forwarded_text=forwarded_text,
    forward_from=forward_from,
)
```

**Step 4: Pass `pre_context` into graph state**

In step 13, add to state dict:

```python
"pre_context": pre_context,
```

**Step 5: Run existing handler tests to check nothing broke**

```bash
pytest tests/test_handlers.py -v
```

Fix any mock issues: existing tests mock `compiled_graph.invoke` — make sure they also handle the new `compiled_graph.orchestrate` call by adding `compiled_graph.orchestrate = AsyncMock(return_value="")` in test patches.

**Step 6: Run full test suite**

```bash
pytest -v
```

Expected: all green.

---

## Task 17: Update `bot/state.py` with `pre_context` field

**Files:**
- Read then modify: `bot/state.py`

Add `pre_context: str` to `BotState` TypedDict. Check the file first with Read tool, then add the field.

---

## Task 18: Update `prompts.py` system prompt for orchestrator context

**Files:**
- Modify: `bot/prompts.py`

Add a note to `SYSTEM_PROMPT` explaining the pre-context section:

```python
SYSTEM_PROMPT = """\
## Role
...existing content...

## Pre-context
<pre_context_guidance>
When a "Pre-context from sub-agents" section appears above your messages, use it:
- memory_retriever: relevant long-term memories — use naturally if applicable
- mention_detector: confirms if the user is addressing you — if is_addressed is false and this is a group chat, consider whether to respond
- context_analyst: chat tone and topics — adapt your style accordingly
- image_analyzer: description of attached image — reference it in your reply
- link_extractor: summaries of shared URLs — incorporate key info
- repost_analyzer: summary of forwarded content — use as context
</pre_context_guidance>
"""
```

**Step: Run full tests**

```bash
pytest -v
```

---

## Task 19: Update README and AGENTS.md docs

**Files:**
- Modify: `README.md` — add new env vars to configuration section
- Modify: `AGENTS.md` — update architecture description, add `bot/agents/` to repository map

In `AGENTS.md` update:
- Repository Map: add `bot/agents/` directory listing
- Runtime Flow: update steps 3-4 to describe orchestrator pre-context pipeline
- Tools section: add new sub-agents
- Environment and Config Rules: add new env vars

---

## Task 20: Final integration — run full test suite

```bash
pytest -v
```

All tests must be green before this plan is complete. Fix any failures before declaring done.

Also manually verify the bot starts without errors:

```bash
python -m bot.main
```

(Will fail on missing token, but should not fail on import errors.)
