"""add_scheduled_events

Revision ID: a1b2c3d4e5f6
Revises: b71d5f4a9c2e
Create Date: 2026-03-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "b71d5f4a9c2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduled_events (
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
        "CREATE INDEX IF NOT EXISTS idx_scheduled_events_event_date ON scheduled_events(event_date)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_scheduled_events_chat_id ON scheduled_events(chat_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_scheduled_events_is_active ON scheduled_events(is_active)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS idx_scheduled_events_is_active")
    op.execute("DROP INDEX IF EXISTS idx_scheduled_events_chat_id")
    op.execute("DROP INDEX IF EXISTS idx_scheduled_events_event_date")
    op.execute("DROP TABLE IF EXISTS scheduled_events")
