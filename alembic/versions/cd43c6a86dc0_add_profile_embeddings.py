"""add_profile_embeddings

Revision ID: cd43c6a86dc0
Revises: d6625db46ccf
Create Date: 2026-02-20 22:41:46.435188

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cd43c6a86dc0'
down_revision: Union[str, Sequence[str], None] = 'd6625db46ccf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE user_profiles ADD COLUMN profile_embedding TEXT")


def downgrade() -> None:
    """Downgrade schema."""
    # SQLite has limited ALTER TABLE DROP COLUMN support in older versions,
    # but since this is just an embedding cache, we can drop the column in newer SQLite
    # or recreate the table if we strictly need to downgrade. For simplicity:
    op.execute("ALTER TABLE user_profiles DROP COLUMN profile_embedding")
