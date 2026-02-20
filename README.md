# Telegram Gemini Bot

A Telegram bot powered by Google Gemini AI with real-time web search. Designed for small group chats — it silently reads the conversation for context and answers when tagged. Also works in private chats without any tag.

## Features

- **Google Gemini 2.0 / 1.5** — answers questions using a state-of-the-art LLM
- **Live web search** — uses Gemini's built-in Google Search grounding to find current information
- **Group chat aware** — reads the last 100 messages for context before answering
- **Short answers** — responds in 3–5 sentences, conversational Telegram style
- **Private chat support** — responds to every message in a private chat (no tag needed)
- **Access control** — only responds in whitelisted group chats
- **Self-hosted** — runs as a Docker container on your own hardware (tested on Synology DS224+)

## How It Works

In a **group chat**, the bot silently reads all messages and stores the last 100 as context. When someone tags it (`@botname your question`), it sends the full conversation history to Gemini along with the question and replies in the group.

In a **private chat**, it responds to every message directly — no tag needed.

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
ALLOWED_CHAT_IDS=-100123456789
MAX_HISTORY_MESSAGES=100
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
| `GEMINI_MODEL` | No | `gemini-1.5-flash` | Gemini model to use (see below) |
| `ALLOWED_CHAT_IDS` | Yes | — | Comma-separated list of group chat IDs the bot will respond in |
| `MAX_HISTORY_MESSAGES` | No | `100` | How many messages to keep in memory per chat |

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
```

**In a private chat:**
```
What's the weather like in Kyiv today?
Explain quantum computing in simple terms
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

## Deploying on Synology NAS

1. SSH into your NAS
2. Clone the repo into a folder (e.g. `~/app/horneticus93/`):
   ```bash
   git clone https://github.com/horneticus93/telegram-gemini-bot.git
   ```
3. Create and fill in `.env` as described above
4. Start the bot:
   ```bash
   sudo docker compose up -d
   ```

The container is configured with `restart: unless-stopped`, so it will automatically start again after a NAS reboot or a crash.

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
├── bot/
│   ├── main.py        # Entry point, Telegram bot setup
│   ├── handlers.py    # Message routing and access control
│   ├── gemini.py      # Gemini API client with search grounding
│   └── session.py     # In-memory conversation history
├── tests/             # Unit tests (pytest)
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## License

MIT
