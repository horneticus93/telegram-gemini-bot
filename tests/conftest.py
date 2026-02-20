import os
import tempfile

# Set DB_PATH before any bot module is imported — prevents PermissionError
# when bot.handlers tries to create /app/data/ on macOS during tests
os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(), "test_memory.db"))

import pytest
from alembic.config import Config
from alembic import command

# Run alembic migrations on the test database once before tests
alembic_cfg = Config("alembic.ini")
# Override the sqlalchemy.url to point to our temp test DB
alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{os.environ['DB_PATH']}")
command.upgrade(alembic_cfg, "head")

@pytest.fixture(autouse=True)
def reset_user_memory_db():
    """Reset the shared user_memory DB between tests to prevent state leakage."""
    import sqlite3
    from bot.handlers import user_memory
    with sqlite3.connect(user_memory.db_path) as conn:
        conn.execute("DELETE FROM user_profiles")
        conn.execute("DELETE FROM chat_memberships")
        conn.commit()
    yield
    with sqlite3.connect(user_memory.db_path) as conn:
        conn.execute("DELETE FROM user_profiles")
        conn.execute("DELETE FROM chat_memberships")
        conn.commit()
