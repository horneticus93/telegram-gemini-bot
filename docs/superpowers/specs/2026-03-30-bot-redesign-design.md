# Bot Redesign: Full Architecture Spec

**Date:** 2026-03-30
**Status:** Approved
**Branch:** feature/v2-langgraph-multi-agents-system → new branch `feature/v3-redesign`

---

## Overview

Complete rewrite of the Telegram bot. Goals:
- Remove hard coupling to Gemini — support any LLM provider via LiteLLM
- Replace SQLite + flat memory table with PostgreSQL + Apache AGE graph memory
- Add web admin panel (settings, memory viewer, conversation logs, token stats)
- Simplify architecture: drop LangGraph and the sub-agent orchestrator, use plain async Python with clear layers
- Memory managed by the model itself via tool calls (not a background pipeline)

---

## Architecture

### Layer structure

```
Telegram Update
    ↓
handlers.py        — checks ALLOWED_CHAT_IDS, respond conditions
    ↓
processor.py       — MessageProcessor: detects content type, downloads assets
    ↓
context.py         — ContextBuilder: session history + memory graph search
    ↓
llm.py             — LLMService: LiteLLM call + tool execution loop
    ↓                  tools: memory_add / memory_search / memory_delete /
    ↓                         memory_get_context / web_search
PostgreSQL + AGE   — graph memory writes happen here during tool execution
    ↓
Telegram Reply
    ↓ (background, async)
message_logs table — persisted for admin panel
```

### Project structure

```
bot/
  main.py           — startup: asyncio.gather(telegram polling, uvicorn)
  handlers.py       — Telegram update handler
  processor.py      — MessageProcessor (content type detection + asset fetch)
  context.py        — ContextBuilder (session + memory retrieval)
  llm.py            — LLMService (LiteLLM wrapper + tool loop)
  session.py        — SessionManager (in-memory deque + summarization)
  tools.py          — LiteLLM tool definitions for memory_* and web_search
  config.py         — Settings singleton (DB-backed, hot-reloadable)

memory/
  graph.py          — GraphMemory: Apache AGE Cypher queries
  embeddings.py     — embedding calls via LiteLLM

web/
  main.py           — FastAPI app
  auth.py           — Telegram OAuth + JWT cookie
  routers/
    settings.py     — GET/POST all config
    memory.py       — graph node CRUD
    logs.py         — message logs by chat
    stats.py        — token usage and cost estimates
  static/           — frontend (HTML + JS, Cytoscape.js for graph)

db/
  models.py         — SQLAlchemy models
  migrations/       — Alembic revisions

docker-compose.yml
Dockerfile
```

---

## Message Processing

`MessageProcessor` detects content type and prepares a unified payload for `LLMService`:

| Telegram content | Handling |
|---|---|
| Text only | Pass as-is |
| Photo only | Download bytes via Telegram API → multimodal content |
| Text + photo | Both in one multimodal message |
| URL in text | `httpx.get(url)` → extract page text → inject as context |
| Forwarded message | Include forward metadata (original author, date) + text |
| Multiple URLs | Fetch up to `max_links_per_message` (configurable) |

The model used for vision content is `vision_model` (configurable). For text-only, `chat_model` is used.

---

## LLM Service

`LLMService` wraps LiteLLM and runs the tool execution loop:

```python
response = litellm.completion(
    model=settings.chat_model,      # e.g. "gemini/gemini-2.5-pro"
    messages=context_messages,
    tools=TOOL_DEFINITIONS,
)
# if response has tool_calls → execute → append results → call again
# loop until no tool_calls or max_steps reached
```

Model roles (all configurable in web panel):
- `chat_model` — main conversation
- `vision_model` — messages with images
- `embedding_model` — memory node embeddings
- `summarization_model` — session summarization

**Web search:** without Gemini grounding, `web_search` tool uses [Tavily API](https://tavily.com) (provider-agnostic, designed for LLM agents). `tavily_api_key` added to config. If key is absent, tool returns an error message and the model falls back to its training knowledge.

---

## Graph Memory

### Database: PostgreSQL + Apache AGE extension

AGE graph name: `memory`

**Node labels:**
- `Person` — `{name, aliases[], chat_id, embedding}`
- `Topic` — `{name, description, embedding}`
- `Fact` — `{text, importance, created_at, embedding}`
- `Place` — `{name, embedding}`
- `Event` — `{text, date, embedding}`

**Edge labels:** `KNOWS`, `LIKES`, `DISLIKES`, `IS`, `HAS`, `LIVES_IN`, `WORKS_AT`, `MENTIONS`, `RELATES_TO`, `HAPPENED_AT`, `PART_OF`

All nodes carry: `created_at`, `updated_at`, `source_chat_id`.

**Embedding storage:** AGE does not support pgvector natively. Embeddings are stored in a separate PostgreSQL table using the `pgvector` extension:

```sql
node_embeddings (
  node_id BIGINT PRIMARY KEY,   -- AGE internal node id
  embedding vector(768),        -- pgvector column
  updated_at TIMESTAMP
)
```

Semantic search: query `node_embeddings` with pgvector `<=>` operator → get `node_id` list → fetch full nodes from AGE. This keeps the graph clean and makes similarity search fast even at scale.

### Tools available to the model

```
memory_search(query: str, limit: int = 5)
  → semantic search over node embeddings
  → returns matching nodes with their immediate edges

memory_add(subject: str, relation: str, object: str,
           subject_type: str, object_type: str)
  → upserts a subject→relation→object triple in the graph
  → deduplication: if similar node exists (cosine ≥ 0.85), merges
  → example: ("Oleh", "LIVES_IN", "Berlin", "Person", "Place")

memory_delete(node_id: str)
  → removes node and all its edges

memory_get_context(subject: str)
  → returns the full 2-hop subgraph around the subject
  → used for "what do you know about X?" queries
```

The model calls these tools autonomously — no background pipeline triggers them. If the user says something worth remembering, the model uses `memory_add`. If it needs context, it uses `memory_search` or `memory_get_context`.

---

## PostgreSQL Schema (relational tables)

```sql
-- All bot settings, hot-reloadable
config (
  key VARCHAR PRIMARY KEY,
  value JSONB,
  updated_at TIMESTAMP
)

-- Allowed chats and their bot aliases
chats (
  chat_id BIGINT PRIMARY KEY,
  title VARCHAR,
  bot_aliases TEXT[],
  active BOOLEAN
)

-- Full message log (for admin panel)
message_logs (
  id BIGSERIAL PRIMARY KEY,
  chat_id BIGINT,
  user_id BIGINT,
  username VARCHAR,
  role VARCHAR,          -- 'user' | 'assistant'
  content TEXT,
  content_type VARCHAR,  -- 'text' | 'photo' | 'url' | 'forward'
  tokens_used INTEGER,
  model_used VARCHAR,
  created_at TIMESTAMP
)
```

Schema changes go through Alembic migrations.

---

## Configuration

All settings are stored in the `config` table and editable via the web panel without restart.

**Models:**
- `chat_model` (e.g. `gemini/gemini-2.5-pro`, `openai/gpt-4o`, `ollama/llama3`)
- `vision_model`
- `embedding_model`
- `summarization_model`

**API keys** (stored encrypted with Fernet symmetric encryption; `ENCRYPTION_KEY` env var required at bootstrap):
- `telegram_bot_token`, `gemini_api_key`, `openai_api_key`, `anthropic_api_key`, `openrouter_api_key`

**Session & memory:**
- `max_history_messages`, `summary_threshold`, `summary_max_words`
- `memory_search_limit`, `memory_similarity_threshold`, `max_links_per_message`

**Bot behaviour:**
- `allowed_chat_ids`, `admin_telegram_ids`
- `system_prompt`, `bot_language`
- `respond_in_groups_only_when_mentioned`, `max_response_length`

**Priority:** DB config > ENV vars (bootstrap only: `DATABASE_URL`, `PORT`) > code defaults.

---

## Web Admin Panel

### Pages

| Page | Content |
|---|---|
| Settings | Sections: Models / API keys / Behaviour / Session. Dropdown picks model with provider prefix. Test connection button. Hot-save. |
| Memory | Cytoscape.js graph visualization. Node list with search. Click node → details + edges. Edit / delete. Filter by node type. |
| Logs | Chat selector. Chronological message feed. Shows content type icon, model used, tokens spent. |
| Stats | Token usage by day/week/month. Breakdown by model. Estimated cost. Message count per chat. Memory node count. |

### Telegram OAuth

1. User opens web panel → redirect to `/login`
2. `/login` renders Telegram Login Widget button
3. Telegram sends callback: `{id, first_name, hash, auth_date}`
4. FastAPI verifies: `HMAC-SHA256(data_string, SHA256(BOT_TOKEN))`
5. Checks: `telegram_id ∈ admin_telegram_ids` (from config)
6. Issues JWT as httpOnly cookie (7-day expiry)
7. Redirect to `/settings`

Rejected: unknown `telegram_id` → 403, attempt logged.
Expired JWT → redirect to `/login`.

---

## Deployment

### docker-compose.yml services

```
postgres    — apache/age image (AGE extension built in)
app         — bot + FastAPI in one process (asyncio.gather)
              exposes port 8000 for web panel
nginx       — optional: reverse proxy + HTTPS (Let's Encrypt)
```

### Single-process model

```python
# main.py
await asyncio.gather(
    telegram_app.run_polling(),
    uvicorn.serve(fastapi_app, host="0.0.0.0", port=8000),
)
```

Both the bot and the web panel share the same `db_pool`, `settings` singleton, and `session_manager`.

---

## Session Management

Unchanged from current approach:
- In-memory `deque` per `chat_id`
- Running summary (compressed history when threshold exceeded)
- Recent window (~15 messages) passed as full context to LLM
- `SessionManager` is not persisted to DB (in-memory only, resets on restart)
- All messages also written to `message_logs` table for the admin panel

---

## Testing

- Framework: `pytest` + `pytest-asyncio`
- DB tests use a real PostgreSQL instance (Docker in CI) with Alembic migrations
- No SQLite mocks for DB tests
- LiteLLM calls mocked with `AsyncMock` / `respx` for unit tests
- Tool execution tested independently from LLM calls

---

## What is being removed

- LangGraph (`StateGraph`, `BotState`)
- All sub-agents (`orchestrator.py`, `intent_classifier.py`, `mention_detector.py`, `context_analyst.py`, `image_analyzer.py`, `link_extractor.py`, `repost_analyzer.py`, `memory_watcher.py`, `relevance_judge.py`)
- SQLite + `BotMemory` (flat memories table)
- Complexity classification (simple/complex → flash/pro routing)
- Gemini SDK direct usage (`google-generativeai`)

---

## Open questions (resolved)

| Question | Decision |
|---|---|
| Model provider strategy | LiteLLM — one interface for all providers |
| Web panel scope | Full admin panel: settings + memory + logs + stats |
| Memory control | Model controls graph via tool calls |
| Deployment | Docker Compose: postgres + app + nginx |
| Authentication | Telegram OAuth + JWT cookie |
