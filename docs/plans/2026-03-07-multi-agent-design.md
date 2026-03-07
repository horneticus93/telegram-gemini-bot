# Multi-Agent System Design

**Date:** 2026-03-07
**Branch:** feature/v2-langgraph-redesign
**Status:** Approved

## Goal

Перетворити поточного single-agent Telegram бота на потужну мульти-агентну систему з головним агентом на найкращій моделі та під-агентами на дешевших моделях для витягування контексту, аналізу медіа та прийняття допоміжних рішень.

## Requirements

- Головний агент на `gemini-2.5-pro` (найкраща якість відповіді)
- Під-агенти на `gemini-2.0-flash` або `gemini-2.0-flash-lite` (дешевші задачі)
- Паралельний запуск незалежних під-агентів через `asyncio.gather`
- Затримка відповіді до 15 секунд — прийнятно
- Всі налаштування через env vars з дефолтами
- Бот вивчає своє ім'я в кожному чаті динамічно (зберігає в `chat_config`)

## Models

| Agent | Model | Reason |
|---|---|---|
| Orchestrator (main agent) | `gemini-2.5-pro` | Best reasoning, final answer |
| image_analyzer | `gemini-2.0-flash` | Vision support, cheaper than Pro |
| web_research | `gemini-2.0-flash` | Google Search grounding |
| All other sub-agents | `gemini-2.0-flash-lite` | Max cheap text tasks |

## Architecture: LangGraph Multi-Agent with Hybrid Pre-Context

Підхід A з гібридизацією: деякі під-агенти запускаються завжди паралельно (cheap), інші — тільки якщо є відповідний контент (умовний запуск без LLM перевірки).

### Execution Flow

```
handle_message()
  │
  ├── [без LLM, миттєво]
  │     intent_classifier  (regex/heuristics)
  │
  ├── [asyncio.gather — завжди, паралельно]
  │     memory_retriever  (Flash-Lite) — топ-K релевантних спогадів
  │     mention_detector  (Flash-Lite) — чи звертаються до бота + нові аліаси
  │     context_analyst   (Flash-Lite) — тон, теми, учасники
  │
  ├── [asyncio.gather — умовно, паралельно]
  │     image_analyzer    (Flash)      — якщо message.photo
  │     link_extractor    (Flash-Lite) — якщо URL в тексті
  │     repost_analyzer   (Flash-Lite) — якщо message.forward_date
  │
  ├── Aggregator: збирає pre-context з усіх під-агентів
  │
  └── Головний агент (Pro):
        - отримує оригінальне повідомлення + pre-context
        - може викликати tools: memory_save, memory_watcher, web_research, relevance_judge
        - генерує фінальну відповідь
```

## Sub-Agents Detail

### Always-on (паралельно, Flash-Lite)

| Agent | Input | Output |
|---|---|---|
| `memory_retriever` | current message | top-K relevant memories |
| `mention_detector` | text + chat_aliases from DB | `{is_addressed: bool, confidence: float, new_alias: str|None}` |
| `context_analyst` | last 10 messages | tone, topics, participants |
| `intent_classifier` | current message | type: question/request/joke/complaint/other |

### Conditional (перевірка без LLM)

| Agent | Trigger condition | Model |
|---|---|---|
| `image_analyzer` | `message.photo is not None` | Flash |
| `link_extractor` | `re.search(URL_REGEX, text)` | Flash-Lite |
| `repost_analyzer` | `message.forward_date is not None` | Flash-Lite |

### On-demand tools (викликаються головним агентом)

| Tool | When |
|---|---|
| `memory_watcher` | when important info should be saved |
| `memory_save` | existing tool, kept |
| `web_research` | when fresh info needed |
| `relevance_judge` | filters noise before final answer |

## Bot Alias Learning

Бот динамічно вивчає своє ім'я в кожному чаті:

1. `mention_detector` отримує поточні аліаси для `chat_id` з таблиці `chat_config`
2. Якщо Flash-Lite виявляє нове звернення до бота по невідомому імені — повертає `new_alias`
3. Головний агент через `memory_watcher` зберігає новий аліас в `chat_config`
4. Наступного разу `mention_detector` вже знає це ім'я

## New Database Table

```sql
CREATE TABLE chat_config (
    chat_id    INTEGER PRIMARY KEY,
    bot_aliases TEXT NOT NULL DEFAULT '[]',  -- JSON: ["Гена", "бот"]
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Requires Alembic migration.

## File Structure

```
bot/
  agents/
    __init__.py
    base.py              # BaseSubAgent abstract class
    memory_retriever.py
    memory_watcher.py
    image_analyzer.py
    link_extractor.py
    repost_analyzer.py
    mention_detector.py
    web_research.py
    context_analyst.py
    relevance_judge.py
    intent_classifier.py
  graph.py               # extended: orchestrator receives sub-agent pre-context
  config.py              # new env vars added
  memory.py              # add chat_config read/write methods
```

## Environment Variables

All new vars with defaults:

```bash
# Models
GEMINI_PRO_MODEL=gemini-2.5-pro
GEMINI_FLASH_MODEL=gemini-2.0-flash
GEMINI_FLASH_LITE_MODEL=gemini-2.0-flash-lite

# Agent system
ORCHESTRATOR_TIMEOUT=15          # max seconds for full pipeline
SUBAGENT_TIMEOUT=8               # max seconds per sub-agent
MAX_LINKS_PER_MESSAGE=3          # max URLs to process
MAX_IMAGES_PER_MESSAGE=5         # max photos to process
MENTION_DETECTOR_CONFIDENCE=0.7  # confidence threshold
MEMORY_RETRIEVER_TOP_K=5         # memories to retrieve
RELEVANCE_JUDGE_THRESHOLD=0.6    # relevance filter threshold
```

All added to `.env.example`, `bot/config.py`, `README.md`.

## Testing

- Each sub-agent tested in isolation with mocked LLM
- Integration test: full pipeline with mocked sub-agents
- `chat_config` migration tested with Alembic temp DB pattern
- Existing tests must stay green
