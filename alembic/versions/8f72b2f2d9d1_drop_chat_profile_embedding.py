"""drop_chat_profile_embedding

Revision ID: 8f72b2f2d9d1
Revises: e1b7d9f4c2a1
Create Date: 2026-02-21 17:20:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "8f72b2f2d9d1"
down_revision: Union[str, Sequence[str], None] = "e1b7d9f4c2a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE chat_profiles DROP COLUMN profile_embedding")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE chat_profiles ADD COLUMN profile_embedding TEXT")
