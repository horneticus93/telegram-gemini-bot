# AGENTS Guide for `telegram-gemini-bot`

This file is the primary guidance for AI coding agents working in this repository.
If you edit code here, follow these project-specific rules before generic habits.

## Project Snapshot

- Runtime: async Telegram bot (`python-telegram-bot`) with LangGraph + Gemini.
- Memory model:
  - Short-term: in-memory per-chat session history with summarization (`bot/session.py`).
  - Long-term: global SQLite memories via semantic search (`bot/memory.py`).
- Architecture: Hybrid LangGraph StateGraph + Tool Calling.

## Repository Map

```
bot/main.py       - startup, env validation, Telegram app wiring
bot/config.py     - env vars, constants
bot/handlers.py   - main message handler, invokes LangGraph
bot/graph.py      - LangGraph StateGraph definition
bot/state.py      - BotState TypedDict
bot/tools.py      - memory_search, memory_save, web_search tool factories
bot/memory.py     - SQLite BotMemory (global memories table)
bot/session.py    - in-memory chat history with summarization
bot/prompts.py    - system prompt, summarization prompts
alembic/          - schema migration system
tests/            - pytest suite
```

## Runtime Flow

1. `bot/main.py` validates `TELEGRAM_BOT_TOKEN` and `GEMINI_API_KEY`, inits DB, registers `handle_message`.
2. `handle_message` in `bot/handlers.py`:
   - stores incoming message in session;
   - checks respond conditions (private chat, reply-to-bot, bot mention in group).
3. If responding: builds context (summary + recent messages), invokes LangGraph agent.
4. Agent may use tools: `memory_search`, `memory_save`, `web_search`.
5. Response extracted, sent to Telegram.
6. Background summarization triggered if threshold met.

Do not break this control flow without updating tests accordingly.

## Memory Architecture

- Single `memories` table, no `user_id`/`chat_id` foreign keys.
- Facts reference people by name in the text.
- Semantic search via embedding cosine similarity.
- Scoring: 0.60 semantic + 0.25 recency + 0.15 importance.
- Cooldown anti-repetition.

Notes:
- Embeddings are stored as JSON text, not native vector type.
- Similarity is manual cosine similarity in Python.
- Empty embedding inputs must safely return empty search results.
- SQLite schema must stay aligned with SQL used in `bot/memory.py`.
- Any table/column change requires Alembic migration plus test updates.

## Tools

- `memory_search`: semantic search over the bot's memory store.
- `memory_save`: save a new fact with near-duplicate detection.
- `web_search`: Google Search grounding via Gemini.

## Session Management

- In-memory per-chat history (`deque`).
- Running summaries (compressed history).
- Recent window (~15 messages) for full context.
- History entries are dicts with keys: `role`, `text`, `author`.
- `SessionManager` data is in-memory only and is not stored in SQLite.

## Environment and Config Rules

- Required env vars:
  - `TELEGRAM_BOT_TOKEN`
  - `GEMINI_API_KEY`
  - `ALLOWED_CHAT_IDS`
- Supported config vars with defaults:
  - `GEMINI_MODEL` (default: `gemini-2.5-flash`)
  - `GEMINI_EMBEDDING_MODEL` (default: `gemini-embedding-001`)
  - `MAX_HISTORY_MESSAGES` (default: `50`)
  - `DB_PATH` (default: `/app/data/memory.db`)
- If you introduce/change env vars:
  1. update `.env.example`,
  2. update `README.md` configuration docs,
  3. keep runtime defaults coherent with docs.

## Database and Migration Rules

- Schema changes must go through Alembic revisions in `alembic/versions/`.
- Do not hand-edit live schema outside migration flow.
- Keep `BotMemory` SQL and migration schema synchronized.
- Keep tests migration-friendly (tests currently run Alembic against temporary DBs).

## Testing Standards

- Framework: `pytest` + `pytest-asyncio`.
- Config: `pytest.ini` (`asyncio_mode = auto`).
- Run: `pytest -v`
- Main patterns:
  - `MagicMock` / `AsyncMock` from `unittest.mock`.
  - `patch("bot.handlers....")` for module-level singletons and globals.
  - temporary SQLite DB + Alembic migration setup in tests.

If behavior changes in routing/memory/tools, update or add tests accordingly.

## Common Pitfalls and Edge Cases

- `bot/handlers.py` relies on module-level state (session manager, lazy clients).
- Background tasks can race under heavy message throughput.
- Telegram hard limit of 4096 chars per message is handled manually; preserve splitting behavior.
- Mention/removal and private-chat logic can regress silently if conditions are reordered.
- `ALLOWED_CHAT_IDS` parsing is strict integer parsing from comma-separated env input.

## Code Change Guidelines

- Prefer minimal, behavior-preserving changes unless asked for refactor.
- Keep async boundaries explicit; use `asyncio.to_thread` for blocking work where already used.
- Preserve dependency injection by patchability in tests (avoid hard-wiring runtime singletons).
- Add comments only where logic is subtle (do not add noise comments).
- Keep same style as existing code.
- Any logic change (new behavior, changed flow, changed contract) must be reflected in `AGENTS.md` in the same task.
- Any newly added functionality must be covered by tests in `tests/`.
- After each code change, run relevant tests and ensure existing tests still pass.
- If existing tests fail due to your change, do not ignore them: update/fix implementation and/or tests so the suite is green again.
- Update `AGENTS.md` for any behavior changes.
- Run tests after changes.

## AI Development Pipeline

For structured feature development, use the `/develop` workflow which orchestrates 5 skills in sequence:

1. **Specification** (`.agents/skills/specification/SKILL.md`) -- non-technical spec from user request
2. **Plan** (`.agents/skills/plan/SKILL.md`) -- detailed task-by-task implementation plan
3. **Implementation** (`.agents/skills/implementation/SKILL.md`) -- code + tests, task by task
4. **Review** (`.agents/skills/review/SKILL.md`) -- independent code review with verdict
5. **Testing** (`.agents/skills/testing/SKILL.md`) -- comprehensive tests + full suite verification

Pipeline orchestrator: `.agents/orchestrator.md`
Workflow entry point: `.agents/workflows/develop.md`

Use `/develop` for any non-trivial feature. For small fixes, follow the standard Code Change Guidelines above.

## Completion Checklist

Before declaring task done:

1. Confirm changed files are consistent with runtime flow above.
2. Run relevant pytest subset (or full suite for broad changes).
3. Verify docs are updated for any config/behavior contract changes.
4. Ensure DB changes (if any) include Alembic revision and tests still migrate cleanly.
