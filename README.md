# Telegram Gemini Bot

A Telegram bot powered by Google Gemini AI with real-time web search and persistent user memory. Designed for small group chats — it silently reads the conversation for context, remembers each person over time, and answers when tagged. Also works in private chats without any tag.

## Features

- **Google Gemini 2.0 / 1.5** — answers questions using a state-of-the-art LLM
- **Live web search** — uses Gemini's built-in Google Search grounding to find current information
- **Group chat aware** — reads the last 100 messages for context before answering
- **RAG Semantic Search** — converts chat history into vector embeddings for deep "brain-like" recall of all users
- **Short answers** — responds in 3–5 sentences, conversational Telegram style
- **Private chat support** — responds to every message in a private chat (no tag needed)
- **Persistent user memory** — stores member profiles and embeddings in an Alembic-managed SQLite database
- **Chat member awareness** — knows who is in the chat and answers questions accurately about group members
- **Web UI** — browse and edit user profiles at `http://your-host:8001` via Datasette
- **Access control** — only responds in whitelisted group chats
- **Self-hosted** — runs as Docker containers on your own hardware

## How It Works

In a **group chat**, the bot silently reads all messages and stores the last 100 as context. When someone tags it (`@botname your question`), it sends the full conversation history to Gemini along with the question and replies in the group.

In a **private chat**, it responds to every message directly — no tag needed.

**User Memory & RAG:** After every 10 messages from a person, the bot asks Gemini to update their profile based on recent conversation. It then uses the `gemini-embedding-001` model to calculate a **vector embedding** of this profile and saves it to a persistent SQLite database. 
When anyone asks a question, the bot calculates the embedding of the question and performs a **Cosine Similarity Search** across the database. It instantly retrieves the 3 most relevant profiles and injects them as hidden background context. This makes the bot essentially an omniscient observer of everyone in the chat, regardless of how many members there are.

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

---

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | — | Bot token from @BotFather |
| `GEMINI_API_KEY` | Yes | — | API key from Google AI Studio |
| `GEMINI_MODEL` | No | `gemini-1.5-flash` | Gemini generation model to use (see below) |
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

## User Memory

The bot builds a persistent profile for each person. Profiles are stored in a SQLite database and survive container restarts.

- **Automatic updates** — after every `MEMORY_UPDATE_INTERVAL` messages, the bot updates the profile in the background
- **Immediate update** — say `remember`, `запам'ятай`, or `запомни` to trigger an update right away
- **Injected into responses** — the profile and list of known chat members are included in every Gemini request

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
│   ├── handlers.py    # Message routing, LLM extraction wrapper
│   ├── gemini.py      # Gemini API client (Chat & Embeddings)
│   ├── session.py     # In-memory conversation history
│   └── memory.py      # Persistent Vector DB & SQLite memory
├── tests/             # Unit tests (pytest)
├── Dockerfile         # Bot container (runs alembic on boot)
├── Dockerfile.datasette  # Web UI container
├── docker-compose.yml
└── .env.example
```

---

## License

MIT
