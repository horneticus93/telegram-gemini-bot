import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class UserMemory:
    def __init__(self, db_path: str = "/app/data/memory.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id     INTEGER,
                    chat_id     INTEGER,
                    username    TEXT,
                    first_name  TEXT,
                    profile     TEXT    DEFAULT '',
                    msg_count   INTEGER DEFAULT 0,
                    updated_at  TEXT,
                    PRIMARY KEY (user_id, chat_id)
                )
            """)
            conn.commit()

    def increment_message_count(
        self, user_id: int, chat_id: int, username: str, first_name: str
    ) -> int:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO user_profiles (user_id, chat_id, username, first_name, msg_count)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(user_id, chat_id) DO UPDATE SET
                    msg_count  = msg_count + 1,
                    username   = excluded.username,
                    first_name = excluded.first_name
                """,
                (user_id, chat_id, username, first_name),
            )
            conn.commit()
            row = conn.execute(
                "SELECT msg_count FROM user_profiles WHERE user_id = ? AND chat_id = ?",
                (user_id, chat_id),
            ).fetchone()
            return row[0]

    def get_profile(self, user_id: int, chat_id: int) -> str:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT profile FROM user_profiles WHERE user_id = ? AND chat_id = ?",
                (user_id, chat_id),
            ).fetchone()
            return row[0] if row and row[0] else ""

    def update_profile(self, user_id: int, chat_id: int, profile: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE user_profiles
                SET profile = ?, updated_at = ?
                WHERE user_id = ? AND chat_id = ?
                """,
                (profile, datetime.now(timezone.utc).isoformat(), user_id, chat_id),
            )
            conn.commit()

    def get_chat_members(self, chat_id: int) -> list[str]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT first_name FROM user_profiles WHERE chat_id = ? ORDER BY first_name",
                (chat_id,),
            ).fetchall()
            return [row[0] for row in rows]
