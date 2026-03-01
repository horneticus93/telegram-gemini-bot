# Proactive Bot Design

## Problem

The bot is entirely reactive — it only responds when tagged or in private chats. Users want the bot to feel like a group member: congratulating on dates, starting discussions, addressing people personally, and filling silence.

## Approach

Use python-telegram-bot's built-in `JobQueue` (APScheduler-based) to schedule proactive tasks within the existing bot process. No new services or containers needed.

## New Module

`bot/scheduler.py` — all proactive scheduling and execution logic.

Registered at startup in `bot/main.py` via `JobQueue`.

## Three Types of Proactive Messages

### Type 1: Date Congratulations (`check_dates_job`)

- Runs daily at 09:00 Europe/Kyiv.
- Queries `scheduled_events` table for today's date (MM-DD match for annual events, YYYY-MM-DD for one-time).
- Groups same-type events per chat into a single message (e.g., two birthdays = one combined congratulation).
- Different event types get separate messages.
- Gemini generates personalized congratulations using the person's facts from `memory_facts`.
- Tags the user via @username or Telegram mention.

### Type 2: Engagement / Personal Address (`engagement_job`)

- Runs 1-2 times per day at random times within windows (12:00-15:00 and/or 18:00-21:00 Kyiv time).
- Gemini chooses behavior variant:
  - Throw an interesting question to the whole chat, considering member interests.
  - Address someone personally ("@Oleksiy, you said you love movies — seen the new film X?").
  - Share an interesting fact related to recent discussion topics.
- Input to Gemini: member list + their facts + recent session history.
- Firing probability: ~70% (not every scheduled slot fires).
- Output format: `{"message": "...", "target_user_id": null | int}`.

### Type 3: Silence Breaker (`silence_breaker`)

- After each group message, sets a delayed timer (5-10 minutes, randomized).
- Each new message resets the timer.
- When timer fires: 50% probability of responding.
- Gemini receives last N messages from session + author facts.
- Generates a natural reaction to the conversation or changes topic.

## New Database Table: `scheduled_events`

```sql
CREATE TABLE scheduled_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER,
    chat_id         INTEGER NOT NULL,
    event_type      TEXT NOT NULL CHECK(event_type IN ('birthday', 'anniversary', 'custom')),
    event_date      TEXT NOT NULL,       -- 'MM-DD' for annual, 'YYYY-MM-DD' for one-time
    title           TEXT NOT NULL,
    source_fact_id  INTEGER,             -- FK to memory_facts.id
    last_triggered  TEXT,                -- ISO8601, prevents duplicate triggers
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
```

Requires Alembic migration.

## Date Extraction Flow

1. Gemini `extract_facts()` already extracts facts from conversation.
2. After a fact is saved, a new step `extract_date_from_fact()` checks if the fact contains a date.
3. If yes, creates/updates a record in `scheduled_events` automatically.
4. Linked via `source_fact_id` for traceability.

## Gemini Prompts (New Methods in `bot/gemini.py`)

- `generate_congratulation(event_type, persons, person_facts)` — personalized congratulation.
- `generate_engagement(members, member_facts, recent_history)` — discussion starter or personal address.
- `generate_silence_response(recent_messages, author_facts)` — natural conversation continuation.
- `extract_date_from_fact(fact_text)` — structured date extraction from fact text.

All prompts maintain the bot's existing tone (short, conversational, Telegram style).

## Safety Mechanisms

- **Daily limit**: max 4 proactive messages per chat per day (configurable).
- **Night mode**: no messages between 23:00-08:00 Europe/Kyiv.
- **Date deduplication**: `last_triggered` field prevents congratulating twice.
- **Daily counter**: in-memory dict tracking proactive messages sent per chat per day, resets at midnight.

## New Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PROACTIVE_ENABLED` | `false` | Master switch for proactive features |
| `PROACTIVE_TIMEZONE` | `Europe/Kyiv` | Timezone for scheduling |
| `PROACTIVE_DAILY_LIMIT` | `4` | Max proactive messages per chat per day |
| `PROACTIVE_SILENCE_MINUTES` | `7` | Minutes of silence before potential response |
| `PROACTIVE_SILENCE_PROBABILITY` | `0.5` | Probability of responding to silence |

## Data Flow

```
JobQueue timer fires
  -> scheduler.py fetches relevant data (facts, members, events)
  -> builds context-specific Gemini prompt
  -> Gemini generates proactive message
  -> scheduler.py sends via bot.send_message()
  -> updates tracking (daily counter, last_triggered)
```

## Changes to Existing Files

- `bot/main.py` — register scheduler jobs on startup.
- `bot/handlers.py` — reset silence timer on each incoming message.
- `bot/gemini.py` — new prompt methods for proactive content generation.
- `bot/memory.py` — new methods for `scheduled_events` CRUD and date queries.
- `alembic/versions/` — new migration for `scheduled_events` table.
- `.env.example` — new proactive config variables.
- `AGENTS.md` — document proactive system.
- `README.md` — document new features and config.
