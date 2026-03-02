"""Global bot memory backed by SQLite.

The BotMemory class manages a single ``memories`` table.  There are no
user_id / chat_id foreign keys — the bot's memory is global and facts
reference people by name in the text.
"""

import json
import logging
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Module-level helpers ───────────────────────────────────────────────


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(ts: str | None) -> datetime:
    """Parse an ISO timestamp, falling back to *now* on bad input."""
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
    """Clamp *value* to the range [0, 1], returning 0.0 on bad input."""
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, parsed))


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float | None:
    """Cosine similarity between two equal-length vectors.

    Returns ``None`` when inputs are incompatible or a zero-magnitude
    vector is encountered.
    """
    if len(vec_a) != len(vec_b):
        return None
    mag_a = math.sqrt(sum(v * v for v in vec_a))
    mag_b = math.sqrt(sum(v * v for v in vec_b))
    if mag_a == 0 or mag_b == 0:
        return None
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    return dot_product / (mag_a * mag_b)


# ── BotMemory class ───────────────────────────────────────────────────


class BotMemory:
    """Global memory store backed by a single SQLite ``memories`` table."""

    RECENCY_DECAY_DAYS = 14.0
    WEIGHT_SEMANTIC = 0.60
    WEIGHT_RECENCY = 0.25
    WEIGHT_IMPORTANCE = 0.15

    def __init__(self, db_path: str = "/app/data/memory.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    # ── schema ─────────────────────────────────────────────────────

    def init_db(self) -> None:
        """Create the ``memories`` table and enable WAL mode."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    content     TEXT NOT NULL,
                    embedding   TEXT,
                    importance  REAL DEFAULT 0.5,
                    source      TEXT,
                    is_active   INTEGER DEFAULT 1,
                    use_count   INTEGER DEFAULT 0,
                    last_used_at TEXT,
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                )
                """
            )
            conn.commit()

    # ── write operations ───────────────────────────────────────────

    def save_memory(
        self,
        content: str,
        embedding: list[float] | None,
        importance: float = 0.5,
        source: str | None = None,
    ) -> int:
        """Insert a new memory and return its row id."""
        now = _now_iso()
        emb_json = json.dumps(embedding) if embedding else None
        importance = _clamp01(importance)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO memories
                    (content, embedding, importance, source,
                     is_active, use_count, last_used_at,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, 0, NULL, ?, ?)
                """,
                (content, emb_json, importance, source, now, now),
            )
            conn.commit()
            return cursor.lastrowid  # type: ignore[return-value]

    def save_or_update(
        self,
        content: str,
        embedding: list[float] | None,
        importance: float = 0.5,
        source: str | None = None,
        duplicate_threshold: float = 0.85,
    ) -> str:
        """Insert *content* or update an existing near-duplicate.

        Returns ``"updated"`` when a near-duplicate was found and
        refreshed, or ``"inserted"`` when a new row was created.
        """
        if embedding:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT id, embedding
                    FROM memories
                    WHERE is_active = 1
                      AND embedding IS NOT NULL
                    """
                ).fetchall()

            best_id: int | None = None
            best_sim: float = -1.0

            for row_id, emb_str in rows:
                try:
                    stored_emb = json.loads(emb_str)
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
                sim = _cosine_similarity(stored_emb, embedding)
                if sim is not None and sim >= duplicate_threshold and sim > best_sim:
                    best_sim = sim
                    best_id = row_id

            if best_id is not None:
                now = _now_iso()
                emb_json = json.dumps(embedding)
                importance = _clamp01(importance)
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        """
                        UPDATE memories
                        SET content    = ?,
                            embedding  = ?,
                            importance = ?,
                            source     = COALESCE(?, source),
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (content, emb_json, importance, source, now, best_id),
                    )
                    conn.commit()
                return "updated"

        self.save_memory(content, embedding, importance, source)
        return "inserted"

    # ── read / search ──────────────────────────────────────────────

    def search_memories(
        self,
        query_embedding: list[float],
        limit: int = 5,
        min_similarity: float = 0.2,
        cooldown_seconds: int = 900,
    ) -> list[dict]:
        """Semantic search across active memories.

        Returns up to *limit* dicts with keys ``id``, ``content``,
        ``importance``, ``score``.

        Score is a weighted combination:
            0.60 * semantic + 0.25 * recency + 0.15 * importance

        Recency uses exponential decay with a 14-day half-life.
        Memories used within *cooldown_seconds* are excluded.
        """
        if not query_embedding:
            return []

        now_dt = datetime.now(timezone.utc)
        results: list[dict] = []

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT id, content, embedding, importance, last_used_at, updated_at
                FROM memories
                WHERE is_active = 1
                  AND embedding IS NOT NULL
                """
            ).fetchall()

        for row in rows:
            mem_id, content, emb_str, importance, last_used_at, updated_at = row

            try:
                stored_emb = json.loads(emb_str)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

            semantic = _cosine_similarity(stored_emb, query_embedding)
            if semantic is None or semantic < min_similarity:
                continue

            # Cooldown filter
            if last_used_at:
                last_used_dt = _parse_ts(last_used_at)
                if (now_dt - last_used_dt).total_seconds() < cooldown_seconds:
                    continue

            # Recency score (exponential decay, 14-day half-life)
            updated_dt = _parse_ts(updated_at)
            age_days = max((now_dt - updated_dt).total_seconds() / 86400.0, 0.0)
            recency = math.exp(-age_days / self.RECENCY_DECAY_DAYS)

            importance_clamped = _clamp01(importance)

            score = (
                self.WEIGHT_SEMANTIC * semantic
                + self.WEIGHT_RECENCY * recency
                + self.WEIGHT_IMPORTANCE * importance_clamped
            )

            results.append(
                {
                    "id": mem_id,
                    "content": content,
                    "importance": importance_clamped,
                    "score": score,
                }
            )

        results.sort(key=lambda item: item["score"], reverse=True)
        return results[:limit]

    # ── state mutations ────────────────────────────────────────────

    def mark_used(self, memory_ids: list[int]) -> None:
        """Increment ``use_count`` and set ``last_used_at`` for each id."""
        if not memory_ids:
            return
        placeholders = ",".join("?" for _ in memory_ids)
        now = _now_iso()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"""
                UPDATE memories
                SET use_count    = use_count + 1,
                    last_used_at = ?
                WHERE id IN ({placeholders})
                """,
                (now, *memory_ids),
            )
            conn.commit()

    def deactivate(self, memory_id: int) -> None:
        """Soft-delete a memory by setting ``is_active = 0``."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE memories SET is_active = 0, updated_at = ? WHERE id = ?",
                (_now_iso(), memory_id),
            )
            conn.commit()
