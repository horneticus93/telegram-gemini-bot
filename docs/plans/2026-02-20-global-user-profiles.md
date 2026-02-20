# Global User Profiles Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Change user profiles from per-user-per-chat to per-user globally, so a profile built in a group chat is also visible in private and vice versa.

**Architecture:** Split the current `user_profiles` table (composite PK `user_id, chat_id`) into two tables: `user_profiles` (PK `user_id` — global profile) and `chat_memberships` (`user_id, chat_id` — tracks who's been seen where). A `_maybe_migrate` method handles existing data automatically on first boot. `get_profile` and `update_profile` drop the `chat_id` parameter; `get_chat_members` gains a JOIN.

**Tech Stack:** Python `sqlite3` stdlib, pytest.

---

## Task 1: Refactor `bot/memory.py` and `tests/test_memory.py`

**Files:**
- Modify: `bot/memory.py`
- Modify: `tests/test_memory.py`

---

**Step 1: Replace `tests/test_memory.py`** with exactly this content (9 tests — one renamed, one new):

```python
import pytest
from bot.memory import UserMemory


@pytest.fixture
def mem(tmp_path):
    return UserMemory(db_path=str(tmp_path / "test.db"))


def test_first_message_count_is_one(mem):
    count = mem.increment_message_count(user_id=1, chat_id=100, username="alice", first_name="Alice")
    assert count == 1


def test_message_count_accumulates(mem):
    mem.increment_message_count(1, 100, "alice", "Alice")
    mem.increment_message_count(1, 100, "alice", "Alice")
    count = mem.increment_message_count(1, 100, "alice", "Alice")
    assert count == 3


def test_different_users_have_independent_counts(mem):
    mem.increment_message_count(1, 100, "alice", "Alice")
    count = mem.increment_message_count(2, 100, "bob", "Bob")
    assert count == 1


def test_same_user_different_chats_share_count(mem):
    mem.increment_message_count(1, 100, "alice", "Alice")
    count = mem.increment_message_count(1, 200, "alice", "Alice")
    assert count == 2  # global count accumulates across chats


def test_get_profile_unknown_user_returns_empty(mem):
    assert mem.get_profile(user_id=999) == ""


def test_update_and_get_profile(mem):
    mem.increment_message_count(1, 100, "alice", "Alice")
    mem.update_profile(user_id=1, profile="Alice is a software engineer who loves cats.")
    assert mem.get_profile(1) == "Alice is a software engineer who loves cats."


def test_profile_shared_across_chats(mem):
    mem.increment_message_count(1, 100, "alice", "Alice")
    mem.update_profile(user_id=1, profile="Alice loves hiking.")
    mem.increment_message_count(1, 200, "alice", "Alice")  # same user, different chat
    assert mem.get_profile(user_id=1) == "Alice loves hiking."


def test_get_chat_members_returns_known_first_names(mem):
    mem.increment_message_count(1, 100, "alice", "Alice")
    mem.increment_message_count(2, 100, "bob", "Bob")
    mem.increment_message_count(3, 200, "carol", "Carol")  # different chat
    members = mem.get_chat_members(chat_id=100)
    assert set(members) == {"Alice", "Bob"}
    assert "Carol" not in members


def test_get_chat_members_empty_chat_returns_empty(mem):
    assert mem.get_chat_members(chat_id=999) == []
```

**Step 2: Run tests to verify they fail**

```bash
cd /Users/oleksandr/Desktop/horneticus93/telegram-gemini-bot && source .venv/bin/activate && pytest tests/test_memory.py -v
```

Expected: multiple failures — wrong signatures, wrong behavior.

**Step 3: Replace `bot/memory.py`** with exactly this content:

```python
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class UserMemory:
    def __init__(self, db_path: str = "/app/data/memory.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            self._maybe_migrate(conn)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id    INTEGER PRIMARY KEY,
                    username   TEXT,
                    first_name TEXT,
                    profile    TEXT    DEFAULT '',
                    msg_count  INTEGER DEFAULT 0,
                    updated_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_memberships (
                    user_id INTEGER,
                    chat_id INTEGER,
                    PRIMARY KEY (user_id, chat_id)
                )
            """)
            conn.commit()

    def _maybe_migrate(self, conn: sqlite3.Connection) -> None:
        """Migrate from composite (user_id, chat_id) PK to per-user user_id PK."""
        cols = [row[1] for row in conn.execute("PRAGMA table_info(user_profiles)").fetchall()]
        if not cols or "chat_id" not in cols:
            return  # fresh install or already migrated
        logger.info("Migrating user_profiles to per-user schema")
        conn.execute("""
            CREATE TABLE user_profiles_new (
                user_id    INTEGER PRIMARY KEY,
                username   TEXT,
                first_name TEXT,
                profile    TEXT    DEFAULT '',
                msg_count  INTEGER DEFAULT 0,
                updated_at TEXT
            )
        """)
        conn.execute("""
            INSERT INTO user_profiles_new (user_id, username, first_name, profile, msg_count)
            SELECT user_id, username, first_name,
                   MAX(COALESCE(profile, '')),
                   SUM(msg_count)
            FROM user_profiles
            GROUP BY user_id
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_memberships (
                user_id INTEGER,
                chat_id INTEGER,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        conn.execute("""
            INSERT OR IGNORE INTO chat_memberships (user_id, chat_id)
            SELECT DISTINCT user_id, chat_id FROM user_profiles
        """)
        conn.execute("DROP TABLE user_profiles")
        conn.execute("ALTER TABLE user_profiles_new RENAME TO user_profiles")
        conn.commit()
        logger.info("Migration complete")

    def increment_message_count(
        self, user_id: int, chat_id: int, username: str, first_name: str
    ) -> int:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO user_profiles (user_id, username, first_name, msg_count)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                    msg_count  = msg_count + 1,
                    username   = excluded.username,
                    first_name = excluded.first_name
                """,
                (user_id, username, first_name),
            )
            conn.execute(
                "INSERT OR IGNORE INTO chat_memberships (user_id, chat_id) VALUES (?, ?)",
                (user_id, chat_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT msg_count FROM user_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return row[0]

    def get_profile(self, user_id: int) -> str:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT profile FROM user_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            return row[0] if row and row[0] else ""

    def update_profile(self, user_id: int, profile: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE user_profiles
                SET profile = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (profile, datetime.now(timezone.utc).isoformat(), user_id),
            )
            conn.commit()
            if cursor.rowcount == 0:
                logger.warning("update_profile: no row found for user_id=%s", user_id)

    def get_chat_members(self, chat_id: int) -> list[str]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT p.first_name
                FROM user_profiles p
                JOIN chat_memberships m ON p.user_id = m.user_id
                WHERE m.chat_id = ?
                ORDER BY p.first_name
                """,
                (chat_id,),
            ).fetchall()
            return [row[0] for row in rows]
```

**Step 4: Run memory tests to verify all 9 pass**

```bash
cd /Users/oleksandr/Desktop/horneticus93/telegram-gemini-bot && source .venv/bin/activate && pytest tests/test_memory.py -v
```

Expected: 9 passed.

**Step 5: Commit**

```bash
cd /Users/oleksandr/Desktop/horneticus93/telegram-gemini-bot && git add bot/memory.py tests/test_memory.py && git commit -m "feat: global user profiles — split into user_profiles + chat_memberships tables"
```

---

## Task 2: Update `bot/handlers.py` and `tests/test_handlers.py`

**Files:**
- Modify: `bot/handlers.py`
- Modify: `tests/test_handlers.py`

**Step 1: Update `tests/test_handlers.py`** — two tests need updating:

In `test_increments_user_message_count` (around line 114), change:
```python
    profile = user_memory.get_profile(user_id=42, chat_id=10)
```
to:
```python
    profile = user_memory.get_profile(user_id=42)
```

In `test_passes_user_profile_to_gemini` (around line 121-122), change:
```python
    user_memory.increment_message_count(99, 5, "bob", "Bob")  # create row first
    user_memory.update_profile(user_id=99, chat_id=5, profile="Bob is a chef.")
```
to:
```python
    user_memory.increment_message_count(99, 5, "bob", "Bob")  # create row first
    user_memory.update_profile(user_id=99, profile="Bob is a chef.")
```

**Step 2: Run handler tests to verify they fail**

```bash
cd /Users/oleksandr/Desktop/horneticus93/telegram-gemini-bot && source .venv/bin/activate && pytest tests/test_handlers.py -v
```

Expected: failures on `get_profile` and `update_profile` wrong argument count.

**Step 3: Update `bot/handlers.py`** — three lines to change:

In `_update_user_profile`, change:
```python
        existing_profile = user_memory.get_profile(user_id, chat_id)
```
to:
```python
        existing_profile = user_memory.get_profile(user_id)
```

And change:
```python
        user_memory.update_profile(user_id, chat_id, new_profile)
```
to:
```python
        user_memory.update_profile(user_id, new_profile)
```

In `handle_message`, change:
```python
    user_profile = user_memory.get_profile(user.id, chat_id)
```
to:
```python
    user_profile = user_memory.get_profile(user.id)
```

**Step 4: Run full test suite**

```bash
cd /Users/oleksandr/Desktop/horneticus93/telegram-gemini-bot && source .venv/bin/activate && pytest -v
```

Expected: 32 passed (9 memory + 8 gemini + 8 handlers + 7 session).

**Step 5: Commit**

```bash
cd /Users/oleksandr/Desktop/horneticus93/telegram-gemini-bot && git add bot/handlers.py tests/test_handlers.py && git commit -m "feat: update handlers to use global user profiles"
```

---

## Task 3: Push via PR

**Step 1: Push branch and open PR**

```bash
git checkout -b feature/global-user-profiles
git push -u origin feature/global-user-profiles
```

Open PR at: `https://github.com/horneticus93/telegram-gemini-bot/compare/feature/global-user-profiles`

**Step 2: After PR is merged — deploy on NAS**

```bash
cd ~/app/horneticus93/telegram-gemini-bot
git pull
sudo docker compose down
sudo docker compose up -d --build
```

The migration runs automatically on first boot — existing profiles are preserved and merged per user.

Expected in logs on first boot (if data exists):
```
Migrating user_profiles to per-user schema
Migration complete
```
