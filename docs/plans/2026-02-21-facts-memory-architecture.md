# Facts Memory Architecture Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace paragraph-style profile memory with fact-based memory that is retrieved only when relevant, reducing repetitive/aggressive replies.

**Architecture:** Add a new `memory_facts` table for atomic memory entries with metadata (`scope`, `importance`, `confidence`, `last_used_at`). Keep compatibility with current profile flow while switching retrieval and prompt context to fact lists. Use semantic search plus recency/importance reranking and cooldown-based anti-repetition before injecting memory into model calls.

**Tech Stack:** Python, SQLite, Alembic, pytest, python-telegram-bot, Gemini API.

---

### Task 1: Add schema for atomic facts

**Files:**
- Create: `alembic/versions/<new_revision>_add_memory_facts_table.py`
- Test: `tests/test_memory.py`

**Step 1: Write failing test**
- Add tests that expect `UserMemory` to store/retrieve facts and rank them.

**Step 2: Run test to verify it fails**
- Run: `pytest tests/test_memory.py -v`

**Step 3: Write minimal implementation**
- Add migration creating `memory_facts` with indexes.

**Step 4: Run test to verify it passes**
- Run: `pytest tests/test_memory.py -v`

### Task 2: Implement fact extraction and retrieval in memory layer

**Files:**
- Modify: `bot/memory.py`
- Test: `tests/test_memory.py`

**Step 1: Write failing test**
- Add tests for upsert, scoped retrieval, reranking, and cooldown behavior.

**Step 2: Run test to verify it fails**
- Run: `pytest tests/test_memory.py -v`

**Step 3: Write minimal implementation**
- Add `upsert_user_facts`, `upsert_chat_facts`, `search_facts_by_embedding`, `mark_facts_used`.

**Step 4: Run test to verify it passes**
- Run: `pytest tests/test_memory.py -v`

### Task 3: Integrate retrieval policy into handlers

**Files:**
- Modify: `bot/handlers.py`
- Test: `tests/test_handlers.py`

**Step 1: Write failing test**
- Add tests that memory is injected only for high-relevance queries and omitted otherwise.

**Step 2: Run test to verify it fails**
- Run: `pytest tests/test_handlers.py -v`

**Step 3: Write minimal implementation**
- Replace profile retrieval context with fact-based retrieval and usage marking.

**Step 4: Run test to verify it passes**
- Run: `pytest tests/test_handlers.py -v`

### Task 4: Extend Gemini client for facts extraction and safer memory usage

**Files:**
- Modify: `bot/gemini.py`
- Test: `tests/test_gemini.py`

**Step 1: Write failing test**
- Add tests for fact extraction JSON parsing and prompt memory policy text.

**Step 2: Run test to verify it fails**
- Run: `pytest tests/test_gemini.py -v`

**Step 3: Write minimal implementation**
- Add `extract_facts()` and stricter memory usage instructions.

**Step 4: Run test to verify it passes**
- Run: `pytest tests/test_gemini.py -v`

### Task 5: Update project guidance and run full verification

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md` (if behavior docs need updates)

**Step 1: Verification**
- Run: `pytest -v`

**Step 2: Confirm contracts**
- Ensure `GeminiClient.ask()` return type remains `tuple[str, bool]`.

**Step 3: Final review**
- Validate flow in `bot/handlers.py` remains aligned with allowed-chat and response routing logic.
