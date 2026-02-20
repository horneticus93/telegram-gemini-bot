"""initial

Revision ID: d6625db46ccf
Revises: 
Create Date: 2026-02-20 22:41:00.107590

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd6625db46ccf'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id    INTEGER PRIMARY KEY,
            username   TEXT,
            first_name TEXT,
            profile    TEXT    DEFAULT '',
            msg_count  INTEGER DEFAULT 0,
            updated_at TEXT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_memberships (
            user_id INTEGER,
            chat_id INTEGER,
            PRIMARY KEY (user_id, chat_id)
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS chat_memberships")
    op.execute("DROP TABLE IF EXISTS user_profiles")
