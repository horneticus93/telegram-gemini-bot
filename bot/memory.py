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
