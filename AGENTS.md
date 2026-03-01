# AGENTS Guide for `telegram-gemini-bot`

This file is the primary guidance for AI coding agents working in this repository.
If you edit code here, follow these project-specific rules before generic habits.

## Project Snapshot

- Runtime: async Telegram bot (`python-telegram-bot`) with Gemini for generation + embeddings.
- Memory model:
  - Short-term: in-memory chat session history (`bot/session.py`).
  - Long-term: SQLite facts memory + profile compatibility fields via Alembic-managed schema (`bot/memory.py`, `alembic/versions/`).
- Deployment: Docker Compose with two services:
  - `bot` (main app)
  - `datasette` (read/edit DB UI)

## Repository Map

- `bot/main.py` - startup, env validation, Telegram application wiring.
- `bot/handlers.py` - main message orchestration, access control, routing, RAG injection, background profile updates.
- `bot/gemini.py` - Gemini wrapper (`ask`, profile extraction, embedding generation, JSON response parsing).
- `bot/memory.py` - SQLite read/write logic, chat membership tracking, cosine similarity search.
- `bot/session.py` - bounded per-chat message history.
- `alembic/` + `alembic.ini` - schema migration system.
- `tests/` - pytest suite (unit and integration-style tests around handlers/memory/session/gemini contracts).

## Runtime Flow You Must Preserve

1. `bot/main.py` validates `TELEGRAM_BOT_TOKEN` and `GEMINI_API_KEY`, creates app, registers `handle_message`.
2. `handle_message` in `bot/handlers.py`:
   - returns early for invalid/missing message fields;
   - enforces `ALLOWED_CHAT_IDS`;
   - stores incoming message in session;
   - updates user message counters and chat memberships;
   - schedules periodic user profile background updates by interval;
   - responds only when:
     - chat is private, or
     - message is reply-to-bot, or
     - bot mention is present in group.
3. For actual response path:
   - builds question (mention stripped);
   - fetches history + profiles + members;
   - computes query embedding;
   - runs fact retrieval with semantic + recency + importance reranking and cooldown filtering;
   - injects only top relevant facts into model call;
   - parses tuple `(answer, save_to_profile)`;
   - sends Telegram reply (with 4096-char splitting);
   - triggers immediate user facts refresh when flagged.

Do not break this control flow without updating tests accordingly.

## Memory Management UI

The bot provides an interactive inline keyboard UI for managing stored user facts, implemented in `bot/memory_handlers.py`:
- The `/memory` command triggers the UI.
  - In private chats: `/memory [user_id]` targets a specific user.
  - In group chats: `user_id` arguments are ignored (always targets the sender).
- **Callback Routing**: Inline buttons use a prefix scheme (`mem:list:{page}`, `mem:view:{id}`, `mem:del:{id}`, `mem:edit:{id}`).
- **Edit Flow**: When "Edit" is tapped, state is stored in `_pending_edits` dict. The `handle_memory_edit_reply` message handler intercepts the user's next text message and consumes it as the new fact text, bypassing the normal chat flow.

## Proactive Messaging System

The bot can send messages on its own initiative via `bot/scheduler.py`:

- **Date congratulations**: Daily 09:00 check of `scheduled_events` table. Grouped by chat+event_type.
- **Engagement**: 1-2 times/day at random times. Gemini generates discussion starters or personal questions.
- **Silence breaker**: After 5-10 min of no messages, 50% chance the bot responds naturally.

Controlled by `PROACTIVE_ENABLED` env var (default: false). Jobs registered via `JobQueue` in `bot/main.py`.

Safety: daily limit per chat, night mode (23:00-08:00), date deduplication via `last_triggered`.

New files: `bot/scheduler.py`, `tests/test_scheduler.py`.
New table: `scheduled_events` (Alembic migration `a1b2c3d4e5f6`).

## Chat Interaction Logic (Detailed)

Use this mental model when changing `bot/handlers.py`:

- Every incoming text message in allowed chats is first recorded into short-term session memory.
- The bot then decides whether it should answer:
  - private chat: always answer;
  - group chat: answer only if mentioned (`@botname`) or directly replied to.
- If answering, the bot builds a context package:
  - recent per-chat history (`SessionManager`);
  - asking user's persistent profile;
  - known chat members;
  - semantically retrieved profiles from vector search.
- The bot sends this package to Gemini and expects a structured JSON decision:
  - text answer,
  - whether to save/update user profile now.
- Profile updates happen in two ways:
  - periodic background updates by message-count intervals.
  - immediate updates when model flag requests it.

## Non-Negotiable Module Contracts

### `GeminiClient.ask()` (`bot/gemini.py`)

- Return type must stay:
  - `tuple[str, bool]` in order `(answer, save_to_profile)`.
- Model prompt expects strict JSON from the model:
  - `{"answer": "...", "save_to_profile": bool}`
- `_parse_bot_response` must gracefully fall back to plain text when JSON is invalid.

### Session shape (`bot/session.py`)

- History entries are dicts with keys:
  - `role`, `text`, `author`
- `SessionManager` uses rolling window semantics (`deque(maxlen=...)`).

### Memory layer (`bot/memory.py`)

- Embeddings are stored as JSON text, not native vector type.
- Similarity is manual cosine similarity in Python.
- Empty embedding inputs must safely return empty search results.
- `memory_facts` is the primary long-term memory source for retrieval.
- Fact retrieval must preserve relevance gating:
  - semantic threshold,
  - recency/importance reranking,
  - cooldown to avoid repetitive fact injection.
- Fact writes support conflict resolution for near-duplicate facts:
  - resolve against top-K semantically similar existing facts (same owner/scope),
  - then choose deterministic action (`keep_add_new`, `update_existing`, `deactivate_existing`, `noop`).

## SQLite Tables and Their Functions

Current schema (managed by Alembic migrations) includes these tables:

- `user_profiles`
  - Stores one persistent row per user (`user_id` primary key).
  - Holds identity snapshot (`username`, `first_name`), long-term `profile` text, cumulative `msg_count`, optional `profile_embedding`, and `updated_at`.
  - Used for:
    - long-term memory about each person;
    - deciding when periodic user profile refresh should run;
    - semantic retrieval of relevant people during Q&A.

- `chat_memberships`
  - Join table keyed by `(user_id, chat_id)`.
  - Tracks which users have appeared in which chats.
  - Used for building "known members in this chat" context passed to Gemini.

- `memory_facts`
  - Stores atomic memory entries with metadata (scope, importance, confidence, embeddings, last-used markers).
  - Supports `user` scope facts and `chat` scope facts.
  - Used for fact-based retrieval before each model call.
  - Retrieval strategy combines:
    - semantic similarity (embedding cosine),
    - recency decay,
    - importance weighting,
    - cooldown filtering for anti-repetition.

Notes for agents:

- `SessionManager` data is in-memory only and is not stored in SQLite.
- SQLite schema must stay aligned with SQL used in `bot/memory.py`.
- Any table/column change requires Alembic migration plus test updates.

## Why Embeddings Are Needed in This Bot

Embeddings make memory retrieval semantic, not keyword-only.

- Without embeddings, the bot can only use exact text matching or full-profile dumps.
- With embeddings:
  - user profiles are converted to vectors once stored/updated;
  - incoming question is embedded at response time;
  - cosine similarity finds the most semantically relevant profiles;
  - only top relevant memory snippets are injected into the model prompt.

Practical effect:

- Better recall of related facts even when wording differs.
- Smaller, more targeted context sent to Gemini.
- More consistent answers about people/group history across long conversations.

## Environment and Config Rules

- Required env vars:
  - `TELEGRAM_BOT_TOKEN`
  - `GEMINI_API_KEY`
- Supported config vars include:
  - `GEMINI_MODEL`
  - `GEMINI_EMBEDDING_MODEL`
  - `ALLOWED_CHAT_IDS`
  - `MAX_HISTORY_MESSAGES`
  - `MEMORY_UPDATE_INTERVAL`
  - `DB_PATH`
- If you introduce/change env vars:
  1. update `.env.example`,
  2. update `README.md` configuration docs,
  3. keep runtime defaults coherent with docs.

## Database and Migration Rules

- Schema changes must go through Alembic revisions in `alembic/versions/`.
- Do not hand-edit live schema outside migration flow.
- Keep `UserMemory` SQL and migration schema synchronized.
- Keep tests migration-friendly (tests currently run Alembic against temporary DBs).

## Testing Standards in This Repo

- Framework: `pytest` + `pytest-asyncio`.
- Config: `pytest.ini` (`asyncio_mode = auto`).
- Main patterns:
  - `MagicMock` / `AsyncMock` from `unittest.mock`.
  - `patch("bot.handlers....")` for module-level singletons and globals.
  - temporary SQLite DB + Alembic migration setup in tests.

Run at least targeted tests for changed area:

- All tests: `pytest -v`
- Handlers only: `pytest tests/test_handlers.py -v`
- Gemini parsing/client: `pytest tests/test_gemini.py -v`
- Memory behavior: `pytest tests/test_memory.py -v`
- Session behavior: `pytest tests/test_session.py -v`

If behavior changes in routing/memory flags/RAG injection, update or add tests in `tests/test_handlers.py`.

## Common Pitfalls and Edge Cases

- `bot/handlers.py` relies on module-level state (`session_manager`, `user_memory`, `chat_message_counts`, lazy `gemini_client`).
- Background tasks can race under heavy message throughput.
- Telegram hard limit of 4096 chars per message is handled manually; preserve splitting behavior.
- Mention/removal and private-chat logic can regress silently if conditions are reordered.
- `ALLOWED_CHAT_IDS` parsing is strict integer parsing from comma-separated env input.

## Code Change Guidelines for Agents

- Prefer minimal, behavior-preserving changes unless asked for refactor.
- Keep async boundaries explicit; use `asyncio.to_thread` for blocking client/database-heavy work where already used.
- Preserve dependency injection by patchability in tests (avoid hard-wiring runtime singletons).
- Add comments only where logic is subtle (do not add noise comments).
- Any logic change (new behavior, changed flow, changed contract) must be reflected in `AGENTS.md` in the same task.
- Any newly added functionality must be covered by tests in `tests/`.
- After each code change, run relevant tests and ensure existing tests still pass.
- If existing tests fail due to your change, do not ignore them: update/fix implementation and/or tests so the suite is green again.

## AI Development Pipeline

For structured feature development, use the `/develop` workflow which orchestrates 5 skills in sequence:

1. **Specification** (`.agents/skills/specification/SKILL.md`) — non-technical spec from user request
2. **Plan** (`.agents/skills/plan/SKILL.md`) — detailed task-by-task implementation plan
3. **Implementation** (`.agents/skills/implementation/SKILL.md`) — code + tests, task by task
4. **Review** (`.agents/skills/review/SKILL.md`) — independent code review with verdict
5. **Testing** (`.agents/skills/testing/SKILL.md`) — comprehensive tests + full suite verification

Pipeline orchestrator: `.agents/orchestrator.md`
Workflow entry point: `.agents/workflows/develop.md`

Use `/develop` for any non-trivial feature. For small fixes, follow the standard Code Change Guidelines above.

## Completion Checklist

Before declaring task done:

1. Confirm changed files are consistent with runtime flow above.
2. Run relevant pytest subset (or full suite for broad changes).
3. Verify docs are updated for any config/behavior contract changes.
4. Ensure no accidental API contract breaks in `GeminiClient.ask()` tuple semantics.
5. Ensure DB changes (if any) include Alembic revision and tests still migrate cleanly.
