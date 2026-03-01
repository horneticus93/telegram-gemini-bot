import json
import logging
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class UserMemory:
    FACT_RECENCY_DECAY_DAYS = 14.0
    FACT_WEIGHT_SEMANTIC = 0.60
    FACT_WEIGHT_RECENCY = 0.25
    FACT_WEIGHT_IMPORTANCE = 0.15

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

        for uid, name, text, emb in profiles_with_embeddings:
            similarity = _cosine_similarity(emb, query_embedding)
            if similarity is not None:
                results.append((similarity, uid, name, text))
                
        # Sort by similarity descending
        results.sort(key=lambda x: x[0], reverse=True)
        
        # Return only the matched names and text (without similarity score)
        return [(uid, name, text) for _, uid, name, text in results[:limit]]

    def upsert_user_facts(self, user_id: int, chat_id: int, facts: list[dict]) -> None:
        self._upsert_facts(scope="user", user_id=user_id, chat_id=chat_id, facts=facts)

    def upsert_chat_facts(self, chat_id: int, facts: list[dict]) -> None:
        self._upsert_facts(scope="chat", user_id=None, chat_id=chat_id, facts=facts)

    def find_similar_facts(
        self,
        scope: str,
        query_embedding: list[float],
        user_id: int | None = None,
        chat_id: int | None = None,
        limit: int = 3,
        min_semantic: float = 0.35,
    ) -> list[dict]:
        if not query_embedding or scope not in {"user", "chat"}:
            return []
        if scope == "user" and user_id is None:
            return []
        if scope == "chat" and chat_id is None:
            return []

        with sqlite3.connect(self.db_path) as conn:
            if scope == "user":
                rows = conn.execute(
                    """
                    SELECT id, fact_text, embedding
                    FROM memory_facts
                    WHERE is_active = 1
                      AND embedding IS NOT NULL
                      AND scope = 'user'
                      AND user_id = ?
                    """,
                    (user_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, fact_text, embedding
                    FROM memory_facts
                    WHERE is_active = 1
                      AND embedding IS NOT NULL
                      AND scope = 'chat'
                      AND chat_id = ?
                    """,
                    (chat_id,),
                ).fetchall()

        results = []
        for row in rows:
            try:
                fact_id, fact_text, emb_str = row
                fact_embedding = json.loads(emb_str)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            similarity = _cosine_similarity(fact_embedding, query_embedding)
            if similarity is None or similarity < min_semantic:
                continue
            results.append(
                {
                    "fact_id": fact_id,
                    "fact_text": fact_text,
                    "similarity": similarity,
                }
            )
        results.sort(key=lambda item: item["similarity"], reverse=True)
        return results[:limit]

    def _upsert_facts(
        self,
        scope: str,
        user_id: int | None,
        chat_id: int | None,
        facts: list[dict],
    ) -> None:
        if not facts:
            return

        now = _now_iso()
        with sqlite3.connect(self.db_path) as conn:
            for item in facts:
                fact_text = str(item.get("fact") or item.get("fact_text") or "").strip()
                if not fact_text:
                    continue
                importance = _clamp01(item.get("importance", 0.5))
                confidence = _clamp01(item.get("confidence", 0.8))
                embedding = item.get("embedding")
                emb_json = json.dumps(embedding) if embedding else None
                action = str(item.get("action", "keep_add_new")).strip().lower()
                target_fact_id = item.get("target_fact_id")
                try:
                    target_fact_id = int(target_fact_id) if target_fact_id is not None else None
                except (TypeError, ValueError):
                    target_fact_id = None

                if action == "noop":
                    continue

                if action in {"update_existing", "deactivate_existing"} and target_fact_id is not None:
                    target_exists = conn.execute(
                        """
                        SELECT id
                        FROM memory_facts
                        WHERE id = ?
                          AND scope = ?
                          AND COALESCE(user_id, -1) = COALESCE(?, -1)
                          AND COALESCE(chat_id, -1) = COALESCE(?, -1)
                        """,
                        (target_fact_id, scope, user_id, chat_id),
                    ).fetchone()
                    if target_exists:
                        if action == "deactivate_existing":
                            conn.execute(
                                """
                                UPDATE memory_facts
                                SET is_active = 0,
                                    updated_at = ?
                                WHERE id = ?
                                """,
                                (now, target_fact_id),
                            )
                            continue
                        conn.execute(
                            """
                            UPDATE memory_facts
                            SET fact_text = ?,
                                embedding = COALESCE(?, embedding),
                                importance = ?,
                                confidence = ?,
                                is_active = 1,
                                updated_at = ?
                            WHERE id = ?
                            """,
                            (
                                fact_text,
                                emb_json,
                                importance,
                                confidence,
                                now,
                                target_fact_id,
                            ),
                        )
                        continue

                existing = conn.execute(
                    """
                    SELECT id
                    FROM memory_facts
                    WHERE scope = ?
                      AND COALESCE(user_id, -1) = COALESCE(?, -1)
                      AND COALESCE(chat_id, -1) = COALESCE(?, -1)
                      AND fact_text = ?
                    """,
                    (scope, user_id, chat_id, fact_text),
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE memory_facts
                        SET embedding = COALESCE(?, embedding),
                            importance = ?,
                            confidence = ?,
                            is_active = 1,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (emb_json, importance, confidence, now, existing[0]),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO memory_facts (
                            scope, user_id, chat_id, fact_text, embedding,
                            importance, confidence, is_active, use_count,
                            last_used_at, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, NULL, ?, ?)
                        """,
                        (
                            scope,
                            user_id,
                            chat_id,
                            fact_text,
                            emb_json,
                            importance,
                            confidence,
                            now,
                            now,
                        ),
                    )
            conn.commit()

    def get_user_facts(self, user_id: int, limit: int = 30) -> list[str]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT fact_text
                FROM memory_facts
                WHERE scope = 'user'
                  AND user_id = ?
                  AND is_active = 1
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [row[0] for row in rows]

    def get_chat_facts(self, chat_id: int, limit: int = 30) -> list[str]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT fact_text
                FROM memory_facts
                WHERE scope = 'chat'
                  AND chat_id = ?
                  AND is_active = 1
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (chat_id, limit),
            ).fetchall()
        return [row[0] for row in rows]

    def get_user_facts_page(
        self, user_id: int, page: int = 0, page_size: int = 5
    ) -> tuple[list[dict], int]:
        """Return a page of active user-scope facts and total count.

        Returns:
            Tuple of (facts, total_count) where each fact is
            ``{"id": int, "fact_text": str}``.
        """
        offset = page * page_size
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute(
                """
                SELECT COUNT(*)
                FROM memory_facts
                WHERE scope = 'user'
                  AND user_id = ?
                  AND is_active = 1
                """,
                (user_id,),
            ).fetchone()[0]
            rows = conn.execute(
                """
                SELECT id, fact_text
                FROM memory_facts
                WHERE scope = 'user'
                  AND user_id = ?
                  AND is_active = 1
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, page_size, offset),
            ).fetchall()
        facts = [{"id": row[0], "fact_text": row[1]} for row in rows]
        return facts, total

    def delete_fact(self, fact_id: int, user_id: int) -> bool:
        """Delete a user-scope fact by ID. Returns True if a row was deleted."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                DELETE FROM memory_facts
                WHERE id = ?
                  AND user_id = ?
                  AND scope = 'user'
                """,
                (fact_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def update_fact_text(self, fact_id: int, user_id: int, new_text: str) -> bool:
        """Update fact text and clear its embedding. Returns True if updated."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE memory_facts
                SET fact_text = ?,
                    embedding = NULL,
                    updated_at = ?
                WHERE id = ?
                  AND user_id = ?
                  AND scope = 'user'
                """,
                (new_text, _now_iso(), fact_id, user_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def search_facts_by_embedding(
        self,
        query_embedding: list[float],
        chat_id: int,
        asking_user_id: int,
        limit: int = 3,
        min_semantic: float = 0.2,
        cooldown_seconds: int = 900,
    ) -> list[dict]:
        if not query_embedding:
            return []

        now_dt = datetime.now(timezone.utc)
        results = []
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT
                    f.id,
                    f.scope,
                    f.user_id,
                    f.chat_id,
                    f.fact_text,
                    f.embedding,
                    f.importance,
                    f.last_used_at,
                    f.updated_at,
                    p.first_name
                FROM memory_facts f
                LEFT JOIN user_profiles p ON p.user_id = f.user_id
                WHERE f.is_active = 1
                  AND f.embedding IS NOT NULL
                  AND (
                      (f.scope = 'chat' AND f.chat_id = ?)
                      OR (f.scope = 'user' AND f.user_id = ?)
                      OR (
                          f.scope = 'user'
                          AND f.user_id IN (
                              SELECT user_id FROM chat_memberships WHERE chat_id = ?
                          )
                      )
                  )
                """,
                (chat_id, asking_user_id, chat_id),
            ).fetchall()

            for row in rows:
                try:
                    (
                        fact_id,
                        scope,
                        fact_user_id,
                        fact_chat_id,
                        fact_text,
                        emb_str,
                        importance,
                        last_used_at,
                        updated_at,
                        owner_name,
                    ) = row
                    embedding = json.loads(emb_str)
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue

                semantic = _cosine_similarity(embedding, query_embedding)
                if semantic is None or semantic < min_semantic:
                    continue

                if last_used_at:
                    last_used_dt = _parse_ts(last_used_at)
                    if (now_dt - last_used_dt).total_seconds() < cooldown_seconds:
                        continue

                updated_dt = _parse_ts(updated_at)
                age_days = max((now_dt - updated_dt).total_seconds() / 86400.0, 0.0)
                recency = math.exp(-age_days / self.FACT_RECENCY_DECAY_DAYS)
                importance_score = _clamp01(importance)

                score = (
                    self.FACT_WEIGHT_SEMANTIC * semantic
                    + self.FACT_WEIGHT_RECENCY * recency
                    + self.FACT_WEIGHT_IMPORTANCE * importance_score
                )
                results.append(
                    {
                        "fact_id": fact_id,
                        "scope": scope,
                        "user_id": fact_user_id,
                        "chat_id": fact_chat_id,
                        "owner_name": owner_name or "Unknown",
                        "fact_text": fact_text,
                        "semantic_score": semantic,
                        "recency_score": recency,
                        "importance_score": importance_score,
                        "score": score,
                    }
                )

        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:limit]

    def mark_facts_used(self, fact_ids: list[int]) -> None:
        if not fact_ids:
            return
        placeholders = ",".join("?" for _ in fact_ids)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"""
                UPDATE memory_facts
                SET use_count = use_count + 1,
                    last_used_at = ?
                WHERE id IN ({placeholders})
                """,
                (_now_iso(), *fact_ids),
            )
            conn.commit()

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

    def upsert_scheduled_event(
        self,
        user_id: int | None,
        chat_id: int,
        event_type: str,
        event_date: str,
        title: str,
        source_fact_id: int | None = None,
    ) -> None:
        now = _now_iso()
        with sqlite3.connect(self.db_path) as conn:
            existing = conn.execute(
                """
                SELECT id
                FROM scheduled_events
                WHERE COALESCE(user_id, -1) = COALESCE(?, -1)
                  AND chat_id = ?
                  AND event_type = ?
                  AND title = ?
                  AND is_active = 1
                """,
                (user_id, chat_id, event_type, title),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE scheduled_events
                    SET event_date = ?,
                        title = ?,
                        source_fact_id = COALESCE(?, source_fact_id),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (event_date, title, source_fact_id, now, existing[0]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO scheduled_events
                        (user_id, chat_id, event_type, event_date, title,
                         source_fact_id, last_triggered, is_active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, NULL, 1, ?, ?)
                    """,
                    (user_id, chat_id, event_type, event_date, title,
                     source_fact_id, now, now),
                )
            conn.commit()

    def get_events_for_date(self, date_mmdd: str) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, user_id, chat_id, event_type, event_date,
                       title, source_fact_id, last_triggered
                FROM scheduled_events
                WHERE is_active = 1
                  AND (event_date = ? OR event_date LIKE ?)
                ORDER BY chat_id, event_type
                """,
                (date_mmdd, f"%-{date_mmdd}"),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_event_triggered(self, event_id: int) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE scheduled_events
                SET last_triggered = ?
                WHERE id = ?
                """,
                (_now_iso(), event_id),
            )
            conn.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(ts: str | None) -> datetime:
    if not ts:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(ts)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return datetime.now(timezone.utc)


def _clamp01(value: float | int | None) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, parsed))


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float | None:
    if len(vec_a) != len(vec_b):
        return None
    mag_a = math.sqrt(sum(v * v for v in vec_a))
    mag_b = math.sqrt(sum(v * v for v in vec_b))
    if mag_a == 0 or mag_b == 0:
        return None
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    return dot_product / (mag_a * mag_b)

