"""add_chat_config_table

Revision ID: b1f2e3d4c5a6
Revises: a3e7c1d8f5b4
Create Date: 2026-03-07 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = "b1f2e3d4c5a6"
down_revision: Union[str, Sequence[str], None] = "a3e7c1d8f5b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_config (
            chat_id     INTEGER PRIMARY KEY,
            bot_aliases TEXT    NOT NULL DEFAULT '[]',
            created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chat_config")
