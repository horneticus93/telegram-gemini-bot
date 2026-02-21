"""add_chat_profiles

Revision ID: e1b7d9f4c2a1
Revises: cd43c6a86dc0
Create Date: 2026-02-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e1b7d9f4c2a1"
down_revision: Union[str, Sequence[str], None] = "cd43c6a86dc0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_profiles (
            chat_id            INTEGER PRIMARY KEY,
            profile            TEXT    DEFAULT '',
            profile_embedding  TEXT,
            updated_at         TEXT
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS chat_profiles")
