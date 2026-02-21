"""add_memory_facts_table

Revision ID: b71d5f4a9c2e
Revises: f4c9a0a7b2d3
Create Date: 2026-02-21 22:15:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b71d5f4a9c2e"
down_revision: Union[str, Sequence[str], None] = "f4c9a0a7b2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_facts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            scope         TEXT    NOT NULL CHECK(scope IN ('user', 'chat')),
            user_id       INTEGER,
            chat_id       INTEGER,
            fact_text     TEXT    NOT NULL,
            embedding     TEXT,
            importance    REAL    NOT NULL DEFAULT 0.5,
            confidence    REAL    NOT NULL DEFAULT 0.8,
            is_active     INTEGER NOT NULL DEFAULT 1,
            use_count     INTEGER NOT NULL DEFAULT 0,
            last_used_at  TEXT,
            created_at    TEXT    NOT NULL,
            updated_at    TEXT    NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_facts_scope_chat ON memory_facts(scope, chat_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_facts_scope_user ON memory_facts(scope, user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_memory_facts_active ON memory_facts(is_active)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS idx_memory_facts_active")
    op.execute("DROP INDEX IF EXISTS idx_memory_facts_scope_user")
    op.execute("DROP INDEX IF EXISTS idx_memory_facts_scope_chat")
    op.execute("DROP TABLE IF EXISTS memory_facts")
