import json
import logging
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class UserMemory:
    def __init__(self, db_path: str = "/app/data/memory.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # Alembic now handles schema creation; we just ensure WAL mode is on for performance
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")

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

    def update_profile(self, user_id: int, profile: str, embedding: list[float] | None = None) -> None:
        emb_json = json.dumps(embedding) if embedding else None
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE user_profiles
                SET profile = ?, profile_embedding = ?, updated_at = ?
                WHERE user_id = ?
                """,
                (profile, emb_json, datetime.now(timezone.utc).isoformat(), user_id),
            )
            conn.commit()
            if cursor.rowcount == 0:
                logger.warning("update_profile: no row found for user_id=%s", user_id)

    def get_chat_profile(self, chat_id: int) -> str:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT profile FROM chat_profiles WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()
            return row[0] if row and row[0] else ""

    def update_chat_profile(
        self, chat_id: int, profile: str, embedding: list[float] | None = None
    ) -> None:
        emb_json = json.dumps(embedding) if embedding else None
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO chat_profiles (chat_id, profile, profile_embedding, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    profile = excluded.profile,
                    profile_embedding = excluded.profile_embedding,
                    updated_at = excluded.updated_at
                """,
                (chat_id, profile, emb_json, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()

    def search_profiles_by_embedding(self, query_embedding: list[float], limit: int = 5) -> list[tuple[int, str, str]]:
        """Search across all user profiles and return the top `limit` matches based on cosine similarity.

        Returns:
            List of (user_id, first_name, profile) tuples.
        """
        if not query_embedding:
            return []
            
        profiles_with_embeddings = []
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT user_id, first_name, profile, profile_embedding FROM user_profiles "
                "WHERE profile_embedding IS NOT NULL AND profile != ''"
            ).fetchall()
            
            for row in rows:
                try:
                    uid, name, text, emb_str = row
                    emb = json.loads(emb_str)
                    profiles_with_embeddings.append((uid, name, text, emb))
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning("Failed to decode embedding for %s: %s", row[1], e)
                    
        # Calculate cosine similarity
        results = []
        
        # Calculate query magnitude
        query_mag = math.sqrt(sum(v * v for v in query_embedding))
        if query_mag == 0:
            return []
            
        for uid, name, text, emb in profiles_with_embeddings:
            if len(emb) != len(query_embedding):
                continue
                
            dot_product = sum(a * b for a, b in zip(emb, query_embedding))
            emb_mag = math.sqrt(sum(v * v for v in emb))
            
            if emb_mag > 0:
                similarity = dot_product / (query_mag * emb_mag)
                results.append((similarity, uid, name, text))
                
        # Sort by similarity descending
        results.sort(key=lambda x: x[0], reverse=True)
        
        # Return only the matched names and text (without similarity score)
        return [(uid, name, text) for _, uid, name, text in results[:limit]]

    def get_chat_members(self, chat_id: int) -> list[tuple[int, str]]:
        """Return a list of (user_id, first_name) for members in this chat."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT p.user_id, p.first_name
                FROM user_profiles p
                JOIN chat_memberships m ON p.user_id = m.user_id
                WHERE m.chat_id = ?
                ORDER BY p.first_name
                """,
                (chat_id,),
            ).fetchall()
            return [(row[0], row[1]) for row in rows]

    def search_chat_profiles_by_embedding(
        self, query_embedding: list[float], limit: int = 5
    ) -> list[tuple[int, str]]:
        """Search chat profiles and return top `limit` matches by cosine similarity.

        Returns:
            List of (chat_id, profile) tuples.
        """
        if not query_embedding:
            return []

        profiles_with_embeddings = []
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT chat_id, profile, profile_embedding FROM chat_profiles "
                "WHERE profile_embedding IS NOT NULL AND profile != ''"
            ).fetchall()

            for row in rows:
                try:
                    chat_id, text, emb_str = row
                    emb = json.loads(emb_str)
                    profiles_with_embeddings.append((chat_id, text, emb))
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning("Failed to decode chat embedding for %s: %s", row[0], e)

        query_mag = math.sqrt(sum(v * v for v in query_embedding))
        if query_mag == 0:
            return []

        results = []
        for chat_id, text, emb in profiles_with_embeddings:
            if len(emb) != len(query_embedding):
                continue

            dot_product = sum(a * b for a, b in zip(emb, query_embedding))
            emb_mag = math.sqrt(sum(v * v for v in emb))

            if emb_mag > 0:
                similarity = dot_product / (query_mag * emb_mag)
                results.append((similarity, chat_id, text))

        results.sort(key=lambda x: x[0], reverse=True)
        return [(chat_id, text) for _, chat_id, text in results[:limit]]
