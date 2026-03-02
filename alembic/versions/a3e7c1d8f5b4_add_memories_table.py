"""add_memories_table

Revision ID: a3e7c1d8f5b4
Revises: c3d4e5f6a7b8
Create Date: 2026-03-02 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a3e7c1d8f5b4"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            content     TEXT    NOT NULL,
            embedding   TEXT,
            importance  FLOAT   DEFAULT 0.5,
            source      TEXT,
            is_active   INTEGER DEFAULT 1,
            use_count   INTEGER DEFAULT 0,
            last_used_at TEXT,
            created_at  TEXT    NOT NULL,
            updated_at  TEXT    NOT NULL
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS memories")
