"""add_holiday_event_type

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-03-01 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add 'holiday' to event_type CHECK constraint by recreating the table."""
    op.execute(
        """
        CREATE TABLE scheduled_events_new (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER,
            chat_id         INTEGER NOT NULL,
            event_type      TEXT    NOT NULL CHECK(event_type IN ('birthday', 'anniversary', 'holiday', 'custom')),
            event_date      TEXT    NOT NULL,
            title           TEXT    NOT NULL,
            source_fact_id  INTEGER REFERENCES memory_facts(id),
            last_triggered  TEXT,
            is_active       INTEGER NOT NULL DEFAULT 1,
            created_at      TEXT    NOT NULL,
            updated_at      TEXT    NOT NULL
        )
        """
    )
    op.execute(
        """
        INSERT INTO scheduled_events_new
            (id, user_id, chat_id, event_type, event_date, title,
             source_fact_id, last_triggered, is_active, created_at, updated_at)
        SELECT id, user_id, chat_id, event_type, event_date, title,
               source_fact_id, last_triggered, is_active, created_at, updated_at
        FROM scheduled_events
        """
    )
    op.execute("DROP TABLE scheduled_events")
    op.execute("ALTER TABLE scheduled_events_new RENAME TO scheduled_events")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_scheduled_events_event_date ON scheduled_events(event_date)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_scheduled_events_chat_id ON scheduled_events(chat_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_scheduled_events_is_active ON scheduled_events(is_active)"
    )


def downgrade() -> None:
    """Remove 'holiday' from event_type CHECK constraint."""
    op.execute(
        """
        CREATE TABLE scheduled_events_old (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER,
            chat_id         INTEGER NOT NULL,
            event_type      TEXT    NOT NULL CHECK(event_type IN ('birthday', 'anniversary', 'custom')),
            event_date      TEXT    NOT NULL,
            title           TEXT    NOT NULL,
            source_fact_id  INTEGER REFERENCES memory_facts(id),
            last_triggered  TEXT,
            is_active       INTEGER NOT NULL DEFAULT 1,
            created_at      TEXT    NOT NULL,
            updated_at      TEXT    NOT NULL
        )
        """
    )
    op.execute(
        """
        INSERT INTO scheduled_events_old
            (id, user_id, chat_id, event_type, event_date, title,
             source_fact_id, last_triggered, is_active, created_at, updated_at)
        SELECT id, user_id, chat_id,
               CASE WHEN event_type = 'holiday' THEN 'custom' ELSE event_type END,
               event_date, title,
               source_fact_id, last_triggered, is_active, created_at, updated_at
        FROM scheduled_events
        """
    )
    op.execute("DROP TABLE scheduled_events")
    op.execute("ALTER TABLE scheduled_events_old RENAME TO scheduled_events")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_scheduled_events_event_date ON scheduled_events(event_date)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_scheduled_events_chat_id ON scheduled_events(chat_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_scheduled_events_is_active ON scheduled_events(is_active)"
    )
