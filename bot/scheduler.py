import logging
import os
import random
import re
from collections import defaultdict
from datetime import datetime, date
from zoneinfo import ZoneInfo

from .memory import UserMemory
from .session import SessionManager

logger = logging.getLogger(__name__)

# Config from env
PROACTIVE_ENABLED = os.getenv("PROACTIVE_ENABLED", "false").lower() == "true"
PROACTIVE_TIMEZONE = ZoneInfo(os.getenv("PROACTIVE_TIMEZONE", "Europe/Kyiv"))
PROACTIVE_DAILY_LIMIT = int(os.getenv("PROACTIVE_DAILY_LIMIT", "4"))
PROACTIVE_SILENCE_MINUTES = int(os.getenv("PROACTIVE_SILENCE_MINUTES", "7"))
PROACTIVE_SILENCE_PROBABILITY = float(os.getenv("PROACTIVE_SILENCE_PROBABILITY", "0.5"))


class ProactiveScheduler:
    def __init__(self):
        self._daily_limit = PROACTIVE_DAILY_LIMIT
        self._daily_counts: dict[int, int] = defaultdict(int)  # chat_id -> count
        self._memory: UserMemory | None = None
        self._gemini = None  # set during register
        self._session: SessionManager | None = None

    def _can_send(self, chat_id: int) -> bool:
        return self._daily_counts[chat_id] < self._daily_limit

    def _record_sent(self, chat_id: int) -> None:
        self._daily_counts[chat_id] += 1

    def _is_night_time(self, now: datetime) -> bool:
        return now.hour >= 23 or now.hour < 8

    def reset_daily_counts(self) -> None:
        self._daily_counts.clear()

    async def check_dates(self, bot) -> None:
        now = datetime.now(PROACTIVE_TIMEZONE)
        if self._is_night_time(now):
            return

        today_mmdd = now.strftime("%m-%d")
        today_date = now.strftime("%Y-%m-%d")

        events = self._memory.get_events_for_date(today_mmdd)

        # Filter out events already triggered today
        pending_events = []
        for event in events:
            last = event.get("last_triggered")
            if last and last[:10] == today_date:
                continue
            pending_events.append(event)

        # Group remaining events by (chat_id, event_type)
        groups: dict[tuple[int, str], list[dict]] = defaultdict(list)
        for event in pending_events:
            key = (event["chat_id"], event["event_type"])
            groups[key].append(event)

        for (chat_id, event_type), group_events in groups.items():
            if not self._can_send(chat_id):
                continue

            # Gather person info + facts for each event in this group
            persons = []
            person_facts: dict[str, list[str]] = {}
            for event in group_events:
                user_id = event.get("user_id")
                if user_id is not None:
                    members = self._memory.get_chat_members(chat_id)
                    name = "Unknown"
                    for mid, mname in members:
                        if mid == user_id:
                            name = mname
                            break
                    persons.append({"user_id": user_id, "name": name})
                    facts = self._memory.get_user_facts(user_id)
                    person_facts[str(user_id)] = facts

            message = self._gemini.generate_congratulation(
                event_type=event_type,
                persons=persons,
                person_facts=person_facts,
            )

            await bot.send_message(chat_id=chat_id, text=message)
            self._record_sent(chat_id)

            for event in group_events:
                self._memory.mark_event_triggered(event["id"])

    async def run_engagement(self, bot, chat_id: int) -> None:
        now = datetime.now(PROACTIVE_TIMEZONE)
        if self._is_night_time(now):
            return
        if not self._can_send(chat_id):
            return

        # 70% probability gate
        if random.random() > 0.7:
            return

        members = self._memory.get_chat_members(chat_id)
        member_facts: dict[str, list[str]] = {}
        member_list = []
        for user_id, name in members:
            member_list.append({"user_id": user_id, "name": name})
            facts = self._memory.get_user_facts(user_id)
            member_facts[str(user_id)] = facts

        recent_history = self._session.format_history(chat_id)

        result = self._gemini.generate_engagement(
            members=member_list,
            member_facts=member_facts,
            recent_history=recent_history,
        )

        message = result.get("message", "")
        if not message:
            return

        await bot.send_message(chat_id=chat_id, text=message)
        self._record_sent(chat_id)

    async def break_silence(self, bot, chat_id: int) -> None:
        now = datetime.now(PROACTIVE_TIMEZONE)
        if self._is_night_time(now):
            return
        if not self._can_send(chat_id):
            return

        # Probability gate
        if random.random() > PROACTIVE_SILENCE_PROBABILITY:
            return

        history = self._session.get_history(chat_id)
        if not history:
            return

        # Extract user IDs from author strings ("Name [ID: 123]" format)
        unique_user_ids: set[int] = set()
        for entry in history:
            author = entry.get("author") or ""
            match = re.search(r"\[ID:\s*(\d+)]", author)
            if match:
                unique_user_ids.add(int(match.group(1)))

        # Gather facts for each unique user
        author_facts: dict[str, list[str]] = {}
        for user_id in unique_user_ids:
            facts = self._memory.get_user_facts(user_id)
            author_facts[str(user_id)] = facts

        message = self._gemini.generate_silence_response(
            recent_messages=history,
            author_facts=author_facts,
        )

        if not message:
            return

        await bot.send_message(chat_id=chat_id, text=message)
        self._record_sent(chat_id)


# Module singleton
_scheduler = ProactiveScheduler()


async def check_dates_callback(context):
    await _scheduler.check_dates(context.bot)


async def engagement_callback(context):
    chat_id = context.job.data
    await _scheduler.run_engagement(context.bot, chat_id)


async def silence_callback(context):
    chat_id = context.job.data
    await _scheduler.break_silence(context.bot, chat_id)


async def reset_daily_counts_callback(context):
    _scheduler.reset_daily_counts()


def reset_silence_timer(job_queue, chat_id: int):
    """Reset the silence timer for a chat. Called from handle_message."""
    if not PROACTIVE_ENABLED:
        return
    # Remove existing silence job for this chat
    job_name = f"silence_{chat_id}"
    current_jobs = job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()
    # Schedule new silence job with random delay
    delay_seconds = random.randint(
        PROACTIVE_SILENCE_MINUTES * 60,
        int(PROACTIVE_SILENCE_MINUTES * 1.5) * 60,
    )
    job_queue.run_once(silence_callback, when=delay_seconds, data=chat_id, name=job_name)


def register_jobs(app):
    """Register all proactive jobs on the application's JobQueue."""
    if not PROACTIVE_ENABLED:
        logger.info("Proactive features disabled (PROACTIVE_ENABLED=false)")
        return

    from .handlers import session_manager, gemini_client, ALLOWED_CHAT_IDS

    _scheduler._session = session_manager
    _scheduler._gemini = gemini_client
    _scheduler._memory = UserMemory(db_path=os.getenv("DB_PATH", "/app/data/memory.db"))

    job_queue = app.job_queue

    # Daily date check at 09:00 local time
    job_queue.run_daily(
        check_dates_callback,
        time=datetime.now(PROACTIVE_TIMEZONE).replace(hour=9, minute=0, second=0).timetz(),
        name="check_dates",
    )

    # Engagement jobs for each chat
    for chat_id in ALLOWED_CHAT_IDS:
        afternoon_hour = random.randint(12, 14)
        afternoon_min = random.randint(0, 59)
        job_queue.run_daily(
            engagement_callback,
            time=datetime.now(PROACTIVE_TIMEZONE).replace(hour=afternoon_hour, minute=afternoon_min, second=0).timetz(),
            data=chat_id,
            name=f"engagement_afternoon_{chat_id}",
        )
        evening_hour = random.randint(18, 20)
        evening_min = random.randint(0, 59)
        job_queue.run_daily(
            engagement_callback,
            time=datetime.now(PROACTIVE_TIMEZONE).replace(hour=evening_hour, minute=evening_min, second=0).timetz(),
            data=chat_id,
            name=f"engagement_evening_{chat_id}",
        )

    # Midnight reset
    job_queue.run_daily(
        reset_daily_counts_callback,
        time=datetime.now(PROACTIVE_TIMEZONE).replace(hour=0, minute=0, second=0).timetz(),
        name="reset_daily_counts",
    )

    logger.info("Proactive scheduler registered")
