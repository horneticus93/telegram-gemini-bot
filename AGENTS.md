# AGENTS Guide for `telegram-gemini-bot`

This file is the primary guidance for AI coding agents working in this repository.
If you edit code here, follow these project-specific rules before generic habits.

**Language rule:** All documentation, comments, commit messages, and code in this repository must be written in English.

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
bot/agents/         - sub-agent package
  base.py           - SubAgentResult dataclass, BaseSubAgent
  orchestrator.py   - AgentOrchestrator (wires all sub-agents)
  intent_classifier.py - heuristic intent + complexity detection (no LLM)
  mention_detector.py  - Flash-Lite: detects if bot is addressed
  memory_retriever.py  - Flash-Lite: semantic memory search
  context_analyst.py   - Flash-Lite: tone/topic analysis
  image_analyzer.py    - Flash: vision image description
  link_extractor.py    - Flash-Lite: URL content extraction
  repost_analyzer.py   - Flash-Lite: forwarded message summary
  memory_watcher.py    - Flash-Lite: identifies facts to save
  relevance_judge.py   - Flash-Lite: filters irrelevant results
  prompts.py          - all sub-agent prompts
alembic/          - schema migration system
tests/            - pytest suite
```

## Runtime Flow

1. `bot/main.py` validates `TELEGRAM_BOT_TOKEN` and `GEMINI_API_KEY`, inits DB, registers `handle_message`.
2. `handle_message` in `bot/handlers.py`:
   - stores incoming message in session;
   - checks respond conditions (private chat, reply-to-bot, bot mention in group).
3. After every message (regardless of responding): `_maybe_trigger_memory_watcher()` checks if `RECENT_WINDOW_SIZE` unwatched messages have accumulated. If yes, launches `_run_memory_watcher()` in background.
4. If responding: builds context (summary + recent messages), runs AgentOrchestrator.
5. Orchestrator runs sub-agents in parallel:
   - Always: `intent_classifier` (heuristic, no LLM), `mention_detector`, `memory_retriever`, `context_analyst`
   - Conditional: `image_analyzer` (if photo), `link_extractor` (if URL), `repost_analyzer` (if forward)
   - Results filtered by `relevance_judge` (except `intent_classifier` and `mention_detector`, always kept)
6. Orchestrator returns `(pre_context_brief, complexity)`.
   `complexity = "simple" | "complex"` — from `IntentClassifier` heuristics, no LLM, default `"complex"`.
7. Main agent model selected by complexity:
   - `"simple"` → `gemini-2.0-flash`  (`GEMINI_FLASH_MODEL`)
   - `"complex"` → `gemini-2.5-pro`   (`GEMINI_PRO_MODEL`)
8. Response extracted, sent to Telegram.
9. Background summarization triggered if threshold met.

Do not break this control flow without updating tests accordingly.

## Agent System Architecture

```
Telegram message
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│  handle_message()  [bot/handlers.py]                        │
│                                                             │
│  1. Store in session                                        │
│  2. Check respond conditions                                │
│  3. Detect content: has_photo / has_forward / URLs          │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  AgentOrchestrator  [bot/agents/orchestrator.py]            │
│                                                             │
│  ┌─ ALWAYS (parallel) ───────────────────────────────┐     │
│  │  intent_classifier  (no LLM)  intent + complexity │     │
│  │  mention_detector   Flash-Lite  is bot addressed? │     │
│  │  memory_retriever   Flash-Lite  relevant memories │     │
│  │  context_analyst    Flash-Lite  tone & topics     │     │
│  └───────────────────────────────────────────────────┘     │
│                                                             │
│  ┌─ CONDITIONAL (parallel) ──────────────────────────┐     │
│  │  image_analyzer     Flash       if photo present  │     │
│  │  link_extractor     Flash-Lite  if URL in text    │     │
│  │  repost_analyzer    Flash-Lite  if forwarded msg  │     │
│  └───────────────────────────────────────────────────┘     │
│                                                             │
│  → relevance_judge filters results (Flash-Lite)             │
│  → new bot alias discovered → save to chat_config           │
│  → returns (pre_context_brief, complexity)                  │
└──────────────────────┬──────────────────────────────────────┘
                       │  (pre_context, complexity)
                       ▼
             complexity == "simple"?
                  │           │
                 yes          no
                  │           │
                  ▼           ▼
        gemini-2.0-flash   gemini-2.5-pro
                  │           │
                  └─────┬─────┘
                        ▼
┌─────────────────────────────────────────────────────────────┐
│  Main Agent  [bot/graph.py]                                 │
│                                                             │
│  System prompt = SYSTEM_PROMPT + pre_context brief          │
│                                                             │
│  ┌─ ON-DEMAND tools ─────────────────────────────────┐     │
│  │  memory_save   persist important fact             │     │
│  │  web_search    fetch current information          │     │
│  └───────────────────────────────────────────────────┘     │
│                                                             │
│  → generates final response                                 │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
              Telegram reply
                       │
                       ├──────────────────────────────────────────────────┐
                       ▼ (background, always)                             ▼ (background, if threshold)
      _maybe_trigger_memory_watcher()                         _summarize_chat()  gemini-2.0-flash
               │
               │  every RECENT_WINDOW_SIZE unwatched messages
               ▼
┌─────────────────────────────────────────────────────────────┐
│  MemoryWatcher  [bot/agents/memory_watcher.py]              │
│                                                             │
│  Flash-Lite analyzes the batch of unwatched messages        │
│  → extracts 0–3 important facts (or nothing)               │
│  → saves each fact via BotMemory.save_or_update()           │
│    (near-duplicate detection threshold: cosine ≥ 0.85)      │
│  → advances SessionManager memory-watch pointer             │
└─────────────────────────────────────────────────────────────┘
```

**Models by role:**

| Role | Model | Env var |
|---|---|---|
| Main agent (complex queries) | gemini-2.5-pro | `GEMINI_PRO_MODEL` |
| Main agent (simple queries) | gemini-2.0-flash | `GEMINI_FLASH_MODEL` |
| image_analyzer | gemini-2.0-flash | `GEMINI_FLASH_MODEL` |
| Summarization | gemini-2.0-flash | `GEMINI_FLASH_MODEL` |
| All other sub-agents | gemini-2.0-flash-lite | `GEMINI_FLASH_LITE_MODEL` |
| Embeddings | gemini-embedding-001 | `GEMINI_EMBEDDING_MODEL` |

## Complexity Classification

`IntentClassifier` (`bot/agents/intent_classifier.py`) classifies each query as `simple` or `complex` using pure heuristics (no LLM). Rules evaluated top-to-bottom; first match wins. Default: `complex`.

| Condition | Result |
|---|---|
| `has_photo` / `has_url` / `has_forward` | complex |
| intent == `"request"` | complex |
| `len(text) > 150` | complex |
| technical keyword (UA/EN/RU) | complex |
| web-search keyword (UA/EN/RU) | complex |
| _(none of the above)_ | **simple** |

**Technical keywords:** `функція`, `алгоритм`, `порахуй`, `обчисли`, `поясни`, `перекладіть` / `код`, `code`, `function`, `algorithm`, `calculate`, `explain`, `translate` / `функция`, `алгоритм`, `посчитай`, `объясни`, `переведи`

**Web-search keywords:** `погода`, `ціна`, `новини`, `сьогодні`, `зараз`, `курс` / `weather`, `price`, `news`, `today`, `now`, `rate` / `погода`, `цена`, `новости`, `сегодня`, `сейчас`, `курс`

```
IntentClassifier.run(text, has_photo, has_url, has_forward)
        │
        ▼
  has_photo / has_url / has_forward? ──yes──► complex
        │ no
        ▼
  intent == "request"? ────────────────yes──► complex
        │ no
        ▼
  len(text) > 150? ────────────────────yes──► complex
        │ no
        ▼
  technical keyword match? ────────────yes──► complex
        │ no
        ▼
  web-search keyword match? ───────────yes──► complex
        │ no
        ▼
      simple  ──────────────────────────────► gemini-2.0-flash
    (complex) ──────────────────────────────► gemini-2.5-pro
```

## Passive Memory Watch

The bot observes every message in allowed chats, even when not responding. Facts are extracted and saved in batches:

- **Trigger:** after every message (responding or not), `_maybe_trigger_memory_watcher(chat_id)` checks if the number of **unwatched** messages has reached `RECENT_WINDOW_SIZE`.
- **Batch:** `SessionManager.get_unwatched(chat_id)` returns messages since the last watch pointer. The pointer advances via `mark_memory_watched()` after a successful run.
- **Extraction:** `MemoryWatcher` (Flash-Lite) receives the raw batch and returns 0–3 facts as JSON. If nothing important was said, it returns `[]` and nothing is saved.
- **Dedup:** each fact is embedded and passed to `BotMemory.save_or_update()`. If cosine similarity ≥ 0.85 with an existing memory, the existing record is updated instead of inserting a duplicate.
- **Pointer state:** tracked in `SessionManager._memory_watched_count` (in-memory, per chat, separate from the summarization pointer).

```
Every message
      │
      ▼
_maybe_trigger_memory_watcher(chat_id)
      │
      │  unwatched < RECENT_WINDOW_SIZE?
      │─────────────────────────────────► (skip, return)
      │
      │  unwatched >= RECENT_WINDOW_SIZE
      ▼
_run_memory_watcher(chat_id, messages)   [background task]
      │
      ▼
MemoryWatcher.run(messages)   Flash-Lite
      │
      │  JSON: [{fact, importance}, ...]   (0–3 items, or [])
      ▼
for each fact:
  embed(fact)  →  BotMemory.save_or_update()
                        │
                        ├── cosine(existing) ≥ 0.85 → UPDATE existing row
                        └── no near-duplicate      → INSERT new row
      │
      ▼
SessionManager.mark_memory_watched(chat_id, len(messages))
```

## Memory Architecture

- Single `memories` table, no `user_id`/`chat_id` foreign keys.
- Facts reference people by name in the text.
- Semantic search via embedding cosine similarity.
- Scoring: 0.60 semantic + 0.25 recency + 0.15 importance.
- Cooldown anti-repetition.
- `chat_config` table: per-chat bot alias list (`get_bot_aliases`, `add_bot_alias` in `BotMemory`).
- Bot learns its name in each chat dynamically (stored as JSON list in `chat_config.bot_aliases`).

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
  - `GEMINI_EMBEDDING_MODEL` (default: `gemini-embedding-001`)
  - `MAX_HISTORY_MESSAGES` (default: `50`)
  - `DB_PATH` (default: `/app/data/memory.db`)
  - `GEMINI_PRO_MODEL` (default: `gemini-2.5-pro`) — main agent model
  - `GEMINI_FLASH_MODEL` (default: `gemini-2.0-flash`) — flash sub-agents
  - `GEMINI_FLASH_LITE_MODEL` (default: `gemini-2.0-flash-lite`) — lite sub-agents
  - `ORCHESTRATOR_TIMEOUT` (default: `15`) — max seconds for full pipeline
  - `SUBAGENT_TIMEOUT` (default: `8`) — max seconds per sub-agent
  - `MAX_LINKS_PER_MESSAGE` (default: `3`)
  - `MENTION_DETECTOR_CONFIDENCE` (default: `0.7`)
  - `MEMORY_RETRIEVER_TOP_K` (default: `5`)
  - `RELEVANCE_JUDGE_THRESHOLD` (default: `0.6`)
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
