# AGENTS Guide for `telegram-gemini-bot`

This file is the primary guidance for AI coding agents working in this repository.
If you edit code here, follow these project-specific rules before generic habits.

## Project Snapshot

- Runtime: async Telegram bot (`python-telegram-bot`) with Gemini for generation + embeddings.
- Memory model:
  - Short-term: in-memory chat session history (`bot/session.py`).
  - Long-term: SQLite profiles + embeddings via Alembic-managed schema (`bot/memory.py`, `alembic/versions/`).
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
   - schedules periodic user/chat profile background updates by interval;
   - responds only when:
     - chat is private, or
     - message is reply-to-bot, or
     - bot mention is present in group.
3. For actual response path:
   - builds question (mention stripped);
   - fetches history + profiles + members;
   - computes query embedding;
   - runs vector search and injects retrieved profiles into model call;
   - parses tuple `(answer, save_to_profile, save_to_memory)`;
   - sends Telegram reply (with 4096-char splitting);
   - triggers immediate profile/chat profile refresh when flags are true.

Do not break this control flow without updating tests accordingly.

## Non-Negotiable Module Contracts

### `GeminiClient.ask()` (`bot/gemini.py`)

- Return type must stay:
  - `tuple[str, bool, bool]` in order `(answer, save_to_profile, save_to_memory)`.
- Model prompt expects strict JSON from the model:
  - `{"answer": "...", "save_to_profile": bool, "save_to_memory": bool}`
- `_parse_bot_response` must gracefully fall back to plain text when JSON is invalid.

### Session shape (`bot/session.py`)

- History entries are dicts with keys:
  - `role`, `text`, `author`
- `SessionManager` uses rolling window semantics (`deque(maxlen=...)`).

### Memory layer (`bot/memory.py`)

- Embeddings are stored as JSON text, not native vector type.
- Similarity is manual cosine similarity in Python.
- Empty embedding inputs must safely return empty search results.

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
  - `CHAT_MEMORY_UPDATE_INTERVAL`
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

## Completion Checklist

Before declaring task done:

1. Confirm changed files are consistent with runtime flow above.
2. Run relevant pytest subset (or full suite for broad changes).
3. Verify docs are updated for any config/behavior contract changes.
4. Ensure no accidental API contract breaks in `GeminiClient.ask()` tuple semantics.
5. Ensure DB changes (if any) include Alembic revision and tests still migrate cleanly.
