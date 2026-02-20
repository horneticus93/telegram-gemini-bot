# Telegram Gemini Bot — Design Document

**Date:** 2026-02-20
**Status:** Approved

---

## Overview

A Telegram group bot powered by Google Gemini with built-in Search Grounding. Deployed as a Docker container on a Synology DS224+ NAS. Intended for a small group of users (~2–10 people). The bot silently reads all group messages for context, but only responds when explicitly tagged (`@botname`).

---

## Technology Stack

| Component | Choice |
|---|---|
| Language | Python 3.12 |
| Telegram library | `python-telegram-bot` |
| LLM | Google Gemini (via `google-generativeai` SDK) |
| Internet search | Gemini built-in Search Grounding |
| Hosting | Docker on Synology DS224+ |

---

## Architecture

```
Telegram Group
     │
     ▼
Telegram Bot API  (polling, no webhook needed)
     │
     ▼
[Bot App — Python]
     │
     ├── Message Handler
     │     ├── All messages → append to rolling history buffer
     │     └── @botname tagged → trigger Gemini call
     │
     ├── Session Store (in-memory)
     │     └── chat_id → deque of last 100 messages
     │
     └── Gemini Client
           ├── System prompt (concise response style)
           └── Search Grounding enabled (Google Search)
```

The bot runs as a single Python process using long-polling. No webhook, no port forwarding required on the home network.

---

## Project Structure

```
telegram-gemini-bot/
├── bot/
│   ├── __init__.py
│   ├── main.py          # Entry point, bot setup & polling
│   ├── handlers.py      # Telegram message handlers
│   ├── gemini.py        # Gemini client wrapper (search grounding)
│   └── session.py       # In-memory session/history management
├── docs/
│   └── plans/
│       └── 2026-02-20-telegram-gemini-bot-design.md
├── .env                 # Secrets (not committed to git)
├── .env.example         # Template for secrets
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## Configuration (`.env`)

```
TELEGRAM_BOT_TOKEN=...
GEMINI_API_KEY=...
ALLOWED_CHAT_IDS=-100123456789        # comma-separated group chat IDs
MAX_HISTORY_MESSAGES=100
```

---

## Access Control

The bot is restricted to whitelisted Telegram group chat IDs (configured via `ALLOWED_CHAT_IDS` env var). Messages from any other chat are silently ignored. No per-user authentication is needed.

**Getting the chat ID:** After adding the bot to the group, send any message, then call:
```
https://api.telegram.org/bot<TOKEN>/getUpdates
```
The `chat_id` (negative integer for groups) will appear in the response.

---

## Conversation History

- **Scope:** Per group chat, shared across all members
- **Storage:** In-memory Python `deque` keyed by `chat_id`
- **Window:** Last 100 messages (all group messages, regardless of whether bot was tagged)
- **Format stored:** `[Username]: message text`
- **Reset:** On bot restart (intentional — no persistence needed)

---

## Message Flow

```
Group message arrives
    │
    ├── Is chat_id in ALLOWED_CHAT_IDS? ──NO──► ignore
    │
    └── YES
         ├── Append "[Author]: text" to history deque (max 100)
         │
         ├── Is @botname mentioned? ──NO──► done
         │
         └── YES
              ├── Build Gemini prompt from full history
              ├── Call Gemini API (search grounding enabled)
              └── Reply in group
```

---

## Gemini Integration

**System prompt:**
```
You are a helpful assistant in a Telegram group chat. Keep your responses short
and conversational — maximum 3 to 5 sentences. Write like a person texting,
not like a document. If you need to search the web for current information,
do so, but still summarize briefly.
```

**Search Grounding:** Enabled via `google.generativeai` tools — Gemini automatically decides when to invoke Google Search based on the query.

**Context sent per request:** Full 100-message history + the triggering message, formatted as a conversation transcript.

---

## Error Handling

| Scenario | Behavior |
|---|---|
| Gemini API failure | Reply in group: "Sorry, something went wrong. Try again." |
| Response too long for Telegram (>4096 chars) | Auto-split into multiple messages |
| Bot restart | History resets silently — no user notification |
| Unknown chat | Silently ignore |

---

## Docker Deployment

```yaml
# docker-compose.yml
services:
  bot:
    build: .
    restart: unless-stopped
    env_file: .env
```

`restart: unless-stopped` ensures the bot survives NAS reboots and crashes automatically.

**Dockerfile:** Based on `python:3.12-slim` for a small image footprint suitable for the DS224+.

---

## Intentionally Out of Scope

- Database / persistent history
- Web UI or admin panel
- Per-user conversation threads within the group
- Webhook-based updates (polling is sufficient for home use)
- Long-term memory across sessions
