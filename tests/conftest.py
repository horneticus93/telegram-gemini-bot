import os
import tempfile

# Set DB_PATH before any bot module is imported — prevents PermissionError
# when bot.handlers tries to create /app/data/ on macOS during tests
os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(), "test_memory.db"))

import pytest

@pytest.fixture(autouse=True)
def reset_user_memory_db():
    """Reset the shared user_memory DB between tests to prevent state leakage."""
    import sqlite3
    from bot.handlers import user_memory
    with sqlite3.connect(user_memory.db_path) as conn:
        conn.execute("DELETE FROM user_profiles")
        conn.commit()
    yield
    with sqlite3.connect(user_memory.db_path) as conn:
        conn.execute("DELETE FROM user_profiles")
        conn.commit()
