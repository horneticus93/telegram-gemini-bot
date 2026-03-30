import os
import pytest
import asyncpg
from alembic.config import Config as AlembicConfig
from alembic import command

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://bot:bot@localhost:5432/botdb_test"
)


@pytest.fixture(scope="session", autouse=True)
def run_migrations():
    """Apply Alembic migrations to test DB once per session."""
    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", TEST_DB_URL)
    command.upgrade(cfg, "head")
    yield
    command.downgrade(cfg, "base")


@pytest.fixture
async def pool(run_migrations):
    """asyncpg pool connected to test DB. Used by components that call pool.acquire()."""
    p = await asyncpg.create_pool(TEST_DB_URL, min_size=1, max_size=3)
    yield p
    async with p.acquire() as conn:
        await conn.execute("DELETE FROM message_logs")
        await conn.execute("DELETE FROM config")
        await conn.execute("DELETE FROM chats")
        await conn.execute("DELETE FROM node_embeddings")
    await p.close()


@pytest.fixture
async def db(pool):
    """Single asyncpg connection. Used by components that take a connection directly."""
    async with pool.acquire() as conn:
        yield conn
