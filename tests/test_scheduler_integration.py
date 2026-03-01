"""Integration tests for the proactive scheduler using real DB."""
import sqlite3
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.memory import UserMemory


@pytest.fixture
def integration_memory(tmp_path):
    """Create a real UserMemory with migrated schema."""
    db = str(tmp_path / "test.db")
    from alembic.config import Config
    from alembic import command
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db}")
    command.upgrade(cfg, "head")
    return UserMemory(db_path=db)


def test_full_date_flow(integration_memory):
    """End-to-end: create user, upsert event, query by date, mark triggered."""
    mem = integration_memory
    # Create a user first
    mem.increment_message_count(user_id=1, chat_id=-100, username="olex", first_name="Oleksandr [ID: 1]")

    # Upsert a birthday event
    mem.upsert_scheduled_event(
        user_id=1, chat_id=-100, event_type="birthday",
        event_date="03-10", title="Oleksandr's birthday",
    )

    # Query today's events
    events = mem.get_events_for_date("03-10")
    assert len(events) == 1
    assert events[0]["title"] == "Oleksandr's birthday"
    assert events[0]["last_triggered"] is None

    # Mark triggered
    mem.mark_event_triggered(events[0]["id"])
    events_after = mem.get_events_for_date("03-10")
    assert events_after[0]["last_triggered"] is not None

    # Update same event (user birthday corrected)
    mem.upsert_scheduled_event(
        user_id=1, chat_id=-100, event_type="birthday",
        event_date="03-15", title="Oleksandr's birthday (corrected)",
    )
    old = mem.get_events_for_date("03-10")
    new = mem.get_events_for_date("03-15")
    assert len(old) == 0
    assert len(new) == 1
