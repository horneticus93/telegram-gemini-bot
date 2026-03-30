"""initial schema

Revision ID: 001
Create Date: 2026-03-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, ARRAY

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "config",
        sa.Column("key", sa.String, primary_key=True),
        sa.Column("value", JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table(
        "chats",
        sa.Column("chat_id", sa.BigInteger, primary_key=True),
        sa.Column("title", sa.String),
        sa.Column("bot_aliases", ARRAY(sa.Text), server_default="{}"),
        sa.Column("active", sa.Boolean, server_default="true"),
    )
    op.create_table(
        "message_logs",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("chat_id", sa.BigInteger, nullable=False),
        sa.Column("user_id", sa.BigInteger),
        sa.Column("username", sa.String),
        sa.Column("role", sa.String, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_type", sa.String, server_default="text"),
        sa.Column("tokens_used", sa.Integer),
        sa.Column("model_used", sa.String),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_message_logs_chat_id", "message_logs", ["chat_id"])
    # node_embeddings uses pgvector — raw SQL needed
    op.execute("CREATE TABLE node_embeddings (node_id bigint PRIMARY KEY, embedding vector(768), updated_at timestamptz DEFAULT now())")
    op.execute("CREATE INDEX ON node_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)")


def downgrade() -> None:
    op.drop_table("node_embeddings")
    op.drop_table("message_logs")
    op.drop_table("chats")
    op.drop_table("config")
