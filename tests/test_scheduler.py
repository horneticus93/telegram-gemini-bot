import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


@pytest.fixture
def scheduler():
    """Create a ProactiveScheduler with mocked dependencies."""
    from bot.scheduler import ProactiveScheduler
    s = ProactiveScheduler()
    s._memory = MagicMock()
    s._gemini = MagicMock()
    s._session = MagicMock()
    return s


class TestDailyLimit:
    def test_can_send_when_under_limit(self, scheduler):
        assert scheduler._can_send(chat_id=-100) is True

    def test_cannot_send_when_at_limit(self, scheduler):
        scheduler._daily_limit = 2
        scheduler._daily_counts[-100] = 2
        assert scheduler._can_send(chat_id=-100) is False

    def test_record_sent_increments_count(self, scheduler):
        scheduler._record_sent(chat_id=-100)
        assert scheduler._daily_counts[-100] == 1
        scheduler._record_sent(chat_id=-100)
        assert scheduler._daily_counts[-100] == 2


class TestNightMode:
    def test_night_mode_blocks_at_night(self, scheduler):
        assert scheduler._is_night_time(datetime(2026, 3, 1, 2, 0)) is True

    def test_night_mode_allows_daytime(self, scheduler):
        assert scheduler._is_night_time(datetime(2026, 3, 1, 10, 0)) is False

    def test_night_mode_boundary_8am(self, scheduler):
        assert scheduler._is_night_time(datetime(2026, 3, 1, 8, 0)) is False

    def test_night_mode_boundary_23pm(self, scheduler):
        assert scheduler._is_night_time(datetime(2026, 3, 1, 23, 0)) is True


class TestCheckDates:
    @pytest.mark.asyncio
    async def test_check_dates_sends_congratulation(self, scheduler):
        scheduler._memory.get_events_for_date.return_value = [
            {"id": 1, "user_id": 1, "chat_id": -100, "event_type": "birthday",
             "title": "Olex birthday", "last_triggered": None},
        ]
        scheduler._memory.get_user_facts.return_value = ["loves pizza"]
        scheduler._memory.get_chat_members.return_value = [(1, "Oleksandr")]
        scheduler._gemini.generate_congratulation.return_value = "Happy birthday!"

        bot = AsyncMock()
        fake_now = datetime(2026, 3, 10, 10, 0)
        with patch("bot.scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            await scheduler.check_dates(bot)

        bot.send_message.assert_called_once()
        assert bot.send_message.call_args.kwargs["chat_id"] == -100
        scheduler._memory.mark_event_triggered.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_check_dates_skips_already_triggered_today(self, scheduler):
        scheduler._memory.get_events_for_date.return_value = [
            {"id": 1, "user_id": 1, "chat_id": -100, "event_type": "birthday",
             "title": "Olex birthday", "last_triggered": "2026-03-10T09:00:00"},
        ]
        bot = AsyncMock()
        fake_now = datetime(2026, 3, 10, 10, 0)
        with patch("bot.scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            await scheduler.check_dates(bot)
        bot.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_dates_skips_at_night(self, scheduler):
        bot = AsyncMock()
        fake_now = datetime(2026, 3, 10, 2, 0)  # 2 AM - night
        with patch("bot.scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            await scheduler.check_dates(bot)
        # Should return early, no memory calls
        scheduler._memory.get_events_for_date.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_dates_respects_daily_limit(self, scheduler):
        scheduler._daily_limit = 0  # No sends allowed
        scheduler._memory.get_events_for_date.return_value = [
            {"id": 1, "user_id": 1, "chat_id": -100, "event_type": "birthday",
             "title": "Olex birthday", "last_triggered": None},
        ]
        bot = AsyncMock()
        fake_now = datetime(2026, 3, 10, 10, 0)
        with patch("bot.scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            await scheduler.check_dates(bot)
        bot.send_message.assert_not_called()


class TestResetDailyCounts:
    def test_reset_clears_counts(self, scheduler):
        scheduler._daily_counts[-100] = 5
        scheduler._daily_counts[-200] = 3
        scheduler.reset_daily_counts()
        assert len(scheduler._daily_counts) == 0


class TestBreakSilence:
    @pytest.mark.asyncio
    async def test_break_silence_extracts_user_ids(self, scheduler):
        """Verify that break_silence correctly parses user IDs from author strings."""
        scheduler._session.get_history.return_value = [
            {"role": "user", "text": "hello", "author": "Alice [ID: 111]"},
            {"role": "user", "text": "world", "author": "Bob [ID: 222]"},
            {"role": "user", "text": "again", "author": "Alice [ID: 111]"},
        ]
        scheduler._memory.get_user_facts.return_value = ["some fact"]
        scheduler._gemini.generate_silence_response.return_value = "Hey folks!"

        bot = AsyncMock()
        fake_now = datetime(2026, 3, 10, 12, 0)
        with patch("bot.scheduler.datetime") as mock_dt, \
             patch("bot.scheduler.random") as mock_random:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            mock_random.random.return_value = 0.1  # Below probability threshold
            await scheduler.break_silence(bot, chat_id=-100)

        bot.send_message.assert_called_once()
        # Verify facts were gathered for both unique user IDs
        fact_calls = scheduler._memory.get_user_facts.call_args_list
        called_user_ids = {call.args[0] for call in fact_calls}
        assert called_user_ids == {111, 222}

    @pytest.mark.asyncio
    async def test_break_silence_skips_empty_history(self, scheduler):
        scheduler._session.get_history.return_value = []

        bot = AsyncMock()
        fake_now = datetime(2026, 3, 10, 12, 0)
        with patch("bot.scheduler.datetime") as mock_dt, \
             patch("bot.scheduler.random") as mock_random:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            mock_random.random.return_value = 0.1
            await scheduler.break_silence(bot, chat_id=-100)

        bot.send_message.assert_not_called()


    @pytest.mark.asyncio
    async def test_check_dates_with_user_id_none_event(self, scheduler):
        """Chat-wide events (user_id=None) pass titles and empty persons."""
        scheduler._memory.get_events_for_date.return_value = [
            {"id": 2, "user_id": None, "chat_id": -100, "event_type": "holiday",
             "title": "International Women's Day", "last_triggered": None},
        ]
        scheduler._gemini.generate_congratulation.return_value = "Happy Women's Day!"

        bot = AsyncMock()
        fake_now = datetime(2026, 3, 8, 10, 0)
        with patch("bot.scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            await scheduler.check_dates(bot)

        bot.send_message.assert_called_once()
        call_kwargs = scheduler._gemini.generate_congratulation.call_args.kwargs
        assert call_kwargs["persons"] == []
        assert call_kwargs["titles"] == ["International Women's Day"]
        scheduler._memory.mark_event_triggered.assert_called_once_with(2)

    @pytest.mark.asyncio
    async def test_check_dates_passes_titles(self, scheduler):
        """Titles are collected and passed to generate_congratulation."""
        scheduler._memory.get_events_for_date.return_value = [
            {"id": 1, "user_id": 1, "chat_id": -100, "event_type": "birthday",
             "title": "Olex birthday", "last_triggered": None},
        ]
        scheduler._memory.get_user_facts.return_value = ["loves pizza"]
        scheduler._memory.get_chat_members.return_value = [(1, "Oleksandr")]
        scheduler._gemini.generate_congratulation.return_value = "Happy birthday!"

        bot = AsyncMock()
        fake_now = datetime(2026, 3, 10, 10, 0)
        with patch("bot.scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            await scheduler.check_dates(bot)

        call_kwargs = scheduler._gemini.generate_congratulation.call_args.kwargs
        assert call_kwargs["titles"] == ["Olex birthday"]


class TestRunEngagement:
    @pytest.mark.asyncio
    async def test_run_engagement_sends_message(self, scheduler):
        scheduler._memory.get_chat_members.return_value = [(1, "Alice")]
        scheduler._memory.get_user_facts.return_value = ["likes cats"]
        scheduler._session.format_history.return_value = "[Alice]: hi"
        scheduler._gemini.generate_engagement.return_value = {
            "message": "Hey everyone!",
            "target_user_id": None,
        }

        bot = AsyncMock()
        fake_now = datetime(2026, 3, 10, 12, 0)
        with patch("bot.scheduler.datetime") as mock_dt, \
             patch("bot.scheduler.random") as mock_random:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            mock_random.random.return_value = 0.3  # Below 0.7 threshold
            await scheduler.run_engagement(bot, chat_id=-100)

        bot.send_message.assert_called_once_with(chat_id=-100, text="Hey everyone!")

    @pytest.mark.asyncio
    async def test_run_engagement_skips_by_probability(self, scheduler):
        bot = AsyncMock()
        fake_now = datetime(2026, 3, 10, 12, 0)
        with patch("bot.scheduler.datetime") as mock_dt, \
             patch("bot.scheduler.random") as mock_random:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            mock_random.random.return_value = 0.9  # Above 0.7 threshold
            await scheduler.run_engagement(bot, chat_id=-100)

        bot.send_message.assert_not_called()
