# v2.0.0 Bot Redesign — Design Document

## Goal

Transform the Telegram bot from a simple Q&A assistant into a full community member with its own global memory, using LangGraph for intelligent tool-based interactions and token optimization.

## Key Changes from v1

1. **No `user_id` in DB** — memory is the bot's own, facts reference people by name within text
2. **LangGraph StateGraph + Tool Calling** — hybrid architecture for controlled flow + model agency
3. **Summarization** — periodic chat history compression instead of sending 100 messages
4. **Tool-based interaction** — model decides when to search memory, save facts, or search the web
5. **New DB from scratch** — same `DB_PATH` env var, user changes the value to point to a new file

## Architecture: Hybrid StateGraph + Tool Calling

```
message_in → store_message → should_respond?
                                  ↓ yes
                            build_context (summary + recent ~15 msgs)
                                  ↓
                            agent_node (Gemini + tools: memory_search, memory_save, web_search)
                                  ↓ (may loop for tool calls)
                            send_reply
                                  ↓
                            maybe_summarize (if history > threshold)
```

### Nodes

- **store_message**: Always runs. Saves every incoming message to in-memory session history.
- **router (should_respond)**: Code-level decision (not LLM). Private chat → always respond. Group → only if mentioned or replied to. Same logic as v1.
- **build_context**: Constructs the context package: running summary + last ~15 messages. No memory injection here — model uses `memory_search` tool if needed.
- **agent_node**: Gemini model with bound tools. Can call tools in a loop (ReAct pattern within this node). LangGraph handles the tool call → tool result → model loop automatically.
- **send_reply**: Extracts final text response, sends to Telegram (with 4096-char splitting).
- **maybe_summarize**: If > 30 messages since last summary, calls Gemini to compress history into a running summary.

## Memory Model

### Single table: `memories`

```sql
CREATE TABLE memories (
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
);
```

- **content**: Free-text fact. Model writes full context: "Олександр [ID: 123] в чаті 'Друзі' вегетаріанець з 2024 року"
- **embedding**: JSON-serialized vector for cosine similarity search
- **importance**: 0.0–1.0, set by the model when saving
- **source**: Optional origin info, e.g. "chat:-100123456" (for debugging)
- **is_active**: Soft-delete flag
- **use_count / last_used_at**: For cooldown anti-repetition

### No foreign keys, no user_id, no chat_id columns

Associations are encoded in the fact text itself. Search is purely semantic (embedding cosine similarity). This makes memory truly global — a fact about a user from one chat is available everywhere.

## Tools

### 1. `memory_search(query: str) → list[str]`

- Model calls when it wants to recall something
- Embeds query → cosine similarity search → top-5 results with cooldown filtering
- Returns list of matching fact texts

### 2. `memory_save(memory: str, importance: float = 0.5) → str`

- Model calls when it wants to remember something new
- Creates embedding → checks for near-duplicates (>0.85 similarity)
- If near-duplicate found → updates existing fact
- If not → inserts new fact
- Returns confirmation message

### 3. `web_search(query: str) → str`

- For current information (weather, news, prices)
- Uses Gemini's Google Search grounding
- Returns search results as text

## Session Management & Summarization

### Three layers of context

1. **Running Summary** (persistent per chat, in-memory)
   - When > 30 new messages since last summary → Gemini compresses them into ~200 words
   - Appended to existing summary (capped at ~500 words)
   - Provides long-term conversation context without token cost

2. **Recent Window** (~15 messages)
   - Full messages as multi-turn history
   - Provides immediate context

3. **Semantic Memory** (via `memory_search` tool)
   - Model decides when to search
   - Not automatic — saves tokens when not needed

### Context format sent to model

```
[System prompt]

Conversation summary so far:
<running summary>

[Recent 15 messages as multi-turn history]

[Current user message]
```

Estimated ~70-80% token savings vs current 100-message approach.

## Project Structure

```
bot/
├── main.py          # Entry point, Telegram app wiring
├── handlers.py      # Telegram message handler → invokes graph
├── graph.py         # LangGraph StateGraph definition
├── state.py         # TypedDict for graph state
├── tools.py         # memory_search, memory_save, web_search
├── memory.py        # New DB (memories table), embedding search
├── session.py       # In-memory history + running summaries
├── prompts.py       # System prompt, summarization prompt
└── config.py        # Env vars, constants
```

## Dependencies

### New
- `langchain-google-genai>=2.0.0` — Gemini via LangChain interface
- `langgraph>=0.4.0` — StateGraph + ToolNode
- `langchain-core>=0.3.0` — Base abstractions

### Removed
- `google-genai` — replaced by `langchain-google-genai`

### Kept
- `python-telegram-bot>=21.0,<22.0`
- `python-dotenv>=1.0.0`
- `alembic>=1.13.0`
- `sqlalchemy>=2.0.0`

## Configuration

Same env vars as v1, same `DB_PATH` (user changes the value to point to new DB file):

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | — | Bot token from @BotFather |
| `GEMINI_API_KEY` | Yes | — | API key from Google AI Studio |
| `GEMINI_MODEL` | No | `gemini-3-flash-preview` | Gemini model |
| `GEMINI_EMBEDDING_MODEL` | No | `gemini-embedding-001` | Embedding model |
| `ALLOWED_CHAT_IDS` | Yes | — | Comma-separated chat IDs |
| `MAX_HISTORY_MESSAGES` | No | `50` | Recent messages window (reduced from 100) |
| `DB_PATH` | No | `/app/data/memory.db` | SQLite database path |

## Removed Features (v2.0.0)

- `/memory` command and inline keyboard UI
- `user_profiles` table
- `chat_memberships` table
- `memory_facts` table (replaced by `memories`)
- Per-user profile extraction
- `save_to_profile` JSON response format
- Periodic background profile updates by message count interval
- `MEMORY_UPDATE_INTERVAL` env var

## System Prompt Concept

```
You are a member of a Telegram community. You're helpful, friendly,
and speak naturally like a real person texting. You have your own memory.

Use memory_search to recall things you know about people or past events.
Use memory_save to remember important new facts for the future.
Use web_search to find current information when needed.

When saving memories, always include full context — who, where, what.
Good: "Олександр в чаті 'Програмісти' працює в Google з 2023 року"
Bad: "працює в Google" (missing who and where)

Keep responses short (2-5 sentences). Be conversational, not formal.
Never say you'll look something up later — always answer now.
```
