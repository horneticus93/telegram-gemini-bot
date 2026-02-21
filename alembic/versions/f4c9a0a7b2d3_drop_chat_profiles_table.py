"""drop_chat_profiles_table

Revision ID: f4c9a0a7b2d3
Revises: 8f72b2f2d9d1
Create Date: 2026-02-21 20:10:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f4c9a0a7b2d3"
down_revision: Union[str, Sequence[str], None] = "8f72b2f2d9d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("DROP TABLE IF EXISTS chat_profiles")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_profiles (
            chat_id    INTEGER PRIMARY KEY,
            profile    TEXT    DEFAULT '',
            updated_at TEXT
        )
        """
    )
