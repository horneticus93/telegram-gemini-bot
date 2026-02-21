# Telegram Gemini Bot

A Telegram bot powered by Google Gemini AI with real-time web search and persistent memory. Designed for small group chats — it silently reads the conversation for context, remembers useful long-term facts, and answers when tagged. Also works in private chats without any tag.

## Features

- **Google Gemini 2.0 / 1.5** — answers questions using a state-of-the-art LLM
- **Live web search** — uses Gemini's built-in Google Search grounding to find current information
- **Group chat aware** — reads the last 100 messages for context before answering
- **Fact-based long-term memory** — stores atomic user/chat facts instead of one large profile paragraph
- **Hybrid retrieval ranking** — semantic similarity + recency + importance scoring for better relevance
- **Anti-repetition memory policy** — cooldown prevents injecting the same memory facts every reply
- **Short answers** — responds in 3–5 sentences, conversational Telegram style
- **Private chat support** — responds to every message in a private chat (no tag needed)
- **Persistent memory storage** — stores user/chat facts and embeddings in an Alembic-managed SQLite database
- **Chat member awareness** — knows who is in the chat and answers questions accurately about group members
- **Web UI** — browse and edit user profiles at `http://your-host:8001` via Datasette
- **Access control** — only responds in whitelisted group chats
- **Self-hosted** — runs as Docker containers on your own hardware

## How It Works

In a **group chat**, the bot silently reads all messages and stores the last 100 as context. When someone tags it (`@botname your question`) or replies to the bot, it prepares context and replies in the group.

In a **private chat**, it responds to every message directly — no tag needed.

**Memory & Retrieval (new):**

1. The bot periodically analyzes recent conversation and extracts **atomic facts** in JSON format:
   - `user` facts (stable user preferences/traits),
   - `chat` facts (stable chat-level conventions).
2. Each fact gets an embedding and metadata (`importance`, `confidence`, timestamps).
3. On each response, the bot embeds the current question and retrieves candidate facts.
4. Candidates are ranked by a hybrid score:
   - semantic cosine similarity,
   - recency decay,
   - importance weight.
5. Cooldown filtering removes recently reused facts, reducing repetitive replies.
6. Only top relevant facts are injected into the model prompt.

---

## Requirements

- A Telegram bot token (from [@BotFather](https://t.me/botfather))
- A Google Gemini API key (from [Google AI Studio](https://aistudio.google.com/app/apikey))
- Docker and Docker Compose

---

## Setup

### 1. Create a Telegram bot

1. Open Telegram and message [@BotFather](https://t.me/botfather)
2. Send `/newbot` and follow the prompts
3. Copy the **bot token** (looks like `1234567890:ABCdef...`)

### 2. Get a Gemini API key

1. Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Click **Create API key**
3. Copy the key

### 3. Clone the repository

```bash
git clone https://github.com/horneticus93/telegram-gemini-bot.git
cd telegram-gemini-bot
```

### 4. Create your `.env` file

```bash
cp .env.example .env
```

Edit `.env` and fill in your values:

```env
TELEGRAM_BOT_TOKEN=your_token_here
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-1.5-flash
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
ALLOWED_CHAT_IDS=-100123456789
MAX_HISTORY_MESSAGES=100
MEMORY_UPDATE_INTERVAL=10
DB_PATH=/app/data/memory.db
```

See [Configuration](#configuration) below for details on each variable.

### 5. Find your group chat ID

1. Add your bot to the Telegram group
2. Send any message in the group
3. Open this URL in your browser (replace with your token):
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
4. Find `"chat": {"id": -100XXXXXXXXXX}` in the response — that negative number is your chat ID
5. Set it as `ALLOWED_CHAT_IDS` in `.env`

### 6. Start the bot

```bash
docker compose up -d
```

Check it's running:
```bash
docker compose logs -f
```

You should see: `Bot starting, polling for updates...`

### 7. Database migrations

The app uses Alembic migrations for schema changes (including the new `memory_facts` table).

- In Docker, migrations run automatically on startup.
- For manual/local runs:

```bash
alembic upgrade head
```

---

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | — | Bot token from @BotFather |
| `GEMINI_API_KEY` | Yes | — | API key from Google AI Studio |
| `GEMINI_MODEL` | No | `gemini-3-flash-preview` | Gemini generation model to use (see below) |
| `GEMINI_EMBEDDING_MODEL` | No | `gemini-embedding-001` | Gemini model used for semantic RAG vector embeddings |
| `ALLOWED_CHAT_IDS` | Yes | — | Comma-separated list of group chat IDs the bot will respond in |
| `MAX_HISTORY_MESSAGES` | No | `100` | How many messages to keep in context per chat |
| `MEMORY_UPDATE_INTERVAL` | No | `10` | How many messages between automatic profile updates |
| `DB_PATH` | No | `/app/data/memory.db` | Path to the Alembic-managed SQLite database |

### Available Gemini models

| Model | Speed | Quality | Notes |
|---|---|---|---|
| `gemini-1.5-flash` | Fast | Good | Recommended for most use cases |
| `gemini-1.5-pro` | Slower | Better | Higher quality, lower rate limits |
| `gemini-2.0-flash-001` | Fast | Better | Latest generation, may require paid tier |

To switch models, edit `GEMINI_MODEL` in `.env` and restart the bot — no rebuild needed.

---

## Usage

**In a group chat:**
```
@yourbot what's the current bitcoin price?
@yourbot who won the latest Champions League?
@yourbot what do you think about this?   ← bot uses conversation context
@yourbot remember that I'm a vegetarian  ← updates your profile immediately
```

**In a private chat:**
```
What's the weather like in Kyiv today?
Explain quantum computing in simple terms
```

---

## Memory Architecture

The bot uses a two-layer memory model:

- **Short-term memory** — rolling in-memory chat history (`MAX_HISTORY_MESSAGES`)
- **Long-term memory** — persistent `memory_facts` in SQLite

Long-term memory is fact-based (not one long paragraph). Each fact stores:

- `scope`: `user` or `chat`
- `fact_text`: short atomic statement
- `embedding`: vector for semantic retrieval
- `importance` / `confidence`
- `last_used_at` / `use_count` for anti-repetition

### Memory update flow

- **Automatic updates** — after every `MEMORY_UPDATE_INTERVAL` messages from a user, the bot extracts new facts in the background
- **Immediate update** — when model output sets `save_to_profile=true`, the bot immediately refreshes extracted facts for that user

### Memory injection policy

- Memory is treated as **optional context**, not mandatory text
- The bot injects only the top relevant retrieved facts
- Recently used facts are skipped via cooldown to avoid repetitive answers

### Web UI

A Datasette instance runs alongside the bot and lets you browse and edit profiles in your browser:

```
http://your-host:8001
```

---

## Managing the bot

```bash
# Start
docker compose up -d

# Stop
docker compose down

# Restart (e.g. after changing .env)
docker compose down && docker compose up -d

# Rebuild after a code update
git pull
docker compose down && docker compose up -d --build

# View live logs
docker compose logs -f
```

---

## Troubleshooting

**Bot doesn't respond in the group**
- Make sure the group's chat ID is in `ALLOWED_CHAT_IDS` in `.env`
- Make sure you're tagging the bot with `@exactbotusername`
- Check logs: `docker compose logs -f`

**429 Too Many Requests from Gemini**
- You've hit the API rate limit (15 requests/minute on the free tier)
- Wait a minute and try again
- Consider upgrading to a paid Gemini API plan for heavy usage

**404 Not Found from Gemini**
- The model name in `GEMINI_MODEL` is not available for your API key
- Switch to `gemini-1.5-flash` which works on all free tier keys

**Bot says "I'll get back to you" and never does**
- This is a known LLM quirk — the system prompt already instructs Gemini not to do this
- If it happens, just ask again

---

## Project Structure

```
telegram-gemini-bot/
├── alembic/           # Alembic database migration logic
├── alembic.ini        # Alembic schema configuration
├── bot/
│   ├── main.py        # Entry point, Telegram bot setup
│   ├── handlers.py    # Message routing, memory retrieval, profile/fact updates
│   ├── gemini.py      # Gemini API client (chat, embeddings, fact extraction)
│   ├── session.py     # In-memory conversation history
│   └── memory.py      # SQLite memory layer (profiles, members, memory_facts)
├── tests/             # Unit tests (pytest)
├── Dockerfile         # Bot container (runs alembic on boot)
├── Dockerfile.datasette  # Web UI container
├── docker-compose.yml
└── .env.example
```

---

## License

MIT
