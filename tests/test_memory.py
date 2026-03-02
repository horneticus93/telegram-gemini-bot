"""Tests for bot.memory — BotMemory class and module-level helpers."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from bot.memory import BotMemory, _clamp01, _cosine_similarity, _now_iso, _parse_ts


@pytest.fixture
def mem(tmp_path):
    db_path = str(tmp_path / "test.db")
    m = BotMemory(db_path=db_path)
    m.init_db()
    return m


# ── Helper function tests ──────────────────────────────────────────────


class TestHelpers:
    def test_now_iso_returns_valid_isoformat(self):
        ts = _now_iso()
        parsed = datetime.fromisoformat(ts)
        assert parsed.tzinfo is not None

    def test_parse_ts_roundtrips(self):
        ts = _now_iso()
        dt = _parse_ts(ts)
        assert isinstance(dt, datetime)
        assert dt.tzinfo is not None

    def test_parse_ts_handles_none(self):
        dt = _parse_ts(None)
        assert isinstance(dt, datetime)

    def test_parse_ts_handles_garbage(self):
        dt = _parse_ts("not-a-date")
        assert isinstance(dt, datetime)

    def test_clamp01_normal(self):
        assert _clamp01(0.5) == 0.5

    def test_clamp01_below_zero(self):
        assert _clamp01(-1.0) == 0.0

    def test_clamp01_above_one(self):
        assert _clamp01(2.0) == 1.0

    def test_clamp01_none(self):
        assert _clamp01(None) == 0.0

    def test_clamp01_string(self):
        assert _clamp01("bad") == 0.0

    def test_cosine_similarity_identical(self):
        sim = _cosine_similarity([1.0, 0.0], [1.0, 0.0])
        assert sim is not None
        assert abs(sim - 1.0) < 1e-9

    def test_cosine_similarity_orthogonal(self):
        sim = _cosine_similarity([1.0, 0.0], [0.0, 1.0])
        assert sim is not None
        assert abs(sim) < 1e-9

    def test_cosine_similarity_mismatched_lengths(self):
        assert _cosine_similarity([1.0], [1.0, 0.0]) is None

    def test_cosine_similarity_zero_vector(self):
        assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) is None


# ── BotMemory table creation ───────────────────────────────────────────


class TestInitCreatesTable:
    def test_init_creates_table(self, mem):
        with sqlite3.connect(mem.db_path) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='memories'"
            ).fetchall()
        assert len(rows) == 1

    def test_init_creates_parent_dir(self, tmp_path):
        nested = tmp_path / "deep" / "nested" / "dir"
        db_path = str(nested / "test.db")
        m = BotMemory(db_path=db_path)
        m.init_db()
        assert nested.exists()

    def test_init_sets_wal_mode(self, mem):
        with sqlite3.connect(mem.db_path) as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_table_columns(self, mem):
        with sqlite3.connect(mem.db_path) as conn:
            info = conn.execute("PRAGMA table_info(memories)").fetchall()
        col_names = {row[1] for row in info}
        expected = {
            "id",
            "content",
            "embedding",
            "importance",
            "source",
            "is_active",
            "use_count",
            "last_used_at",
            "created_at",
            "updated_at",
        }
        assert expected == col_names


# ── save_memory + search_memories ──────────────────────────────────────


class TestSaveAndSearch:
    def test_save_and_search(self, mem):
        emb_a = [1.0, 0.0, 0.0]
        emb_b = [0.0, 1.0, 0.0]

        id_a = mem.save_memory(
            content="Alice loves hiking",
            embedding=emb_a,
            importance=0.8,
            source="chat",
        )
        id_b = mem.save_memory(
            content="Bob likes cooking",
            embedding=emb_b,
            importance=0.6,
            source="chat",
        )
        assert isinstance(id_a, int)
        assert isinstance(id_b, int)
        assert id_a != id_b

        results = mem.search_memories(
            query_embedding=[0.9, 0.1, 0.0], limit=5, min_similarity=0.1
        )
        assert len(results) == 2
        # First result should be Alice (closer to query)
        assert results[0]["content"] == "Alice loves hiking"
        assert "score" in results[0]
        assert "id" in results[0]
        assert "importance" in results[0]

    def test_search_returns_empty_for_no_data(self, mem):
        results = mem.search_memories(query_embedding=[1.0, 0.0], limit=5)
        assert results == []

    def test_search_returns_empty_for_empty_embedding(self, mem):
        mem.save_memory(
            content="test memory",
            embedding=[1.0, 0.0],
            importance=0.5,
            source=None,
        )
        results = mem.search_memories(query_embedding=[], limit=5)
        assert results == []

    def test_search_respects_similarity(self, mem):
        """Memories below min_similarity threshold should be excluded."""
        # Opposite vectors: cosine similarity ~ -1
        mem.save_memory(
            content="Opposite direction memory",
            embedding=[-1.0, 0.0, 0.0],
            importance=0.9,
            source="test",
        )
        results = mem.search_memories(
            query_embedding=[1.0, 0.0, 0.0],
            limit=5,
            min_similarity=0.2,
        )
        assert results == []

    def test_search_respects_limit(self, mem):
        for i in range(10):
            mem.save_memory(
                content=f"Memory {i}",
                embedding=[1.0, float(i) / 100.0],
                importance=0.5,
                source="test",
            )
        results = mem.search_memories(
            query_embedding=[1.0, 0.0],
            limit=3,
        )
        assert len(results) == 3

    def test_search_excludes_inactive(self, mem):
        mid = mem.save_memory(
            content="Will be deactivated",
            embedding=[1.0, 0.0],
            importance=0.5,
            source="test",
        )
        mem.deactivate(mid)
        results = mem.search_memories(query_embedding=[1.0, 0.0], limit=5)
        assert results == []


# ── Cooldown filtering ─────────────────────────────────────────────────


class TestSearchWithCooldown:
    def test_search_with_cooldown(self, mem):
        mid = mem.save_memory(
            content="Recently used fact",
            embedding=[1.0, 0.0],
            importance=0.8,
            source="test",
        )
        # Mark as used now
        mem.mark_used([mid])

        # Should be filtered by cooldown (default 900 seconds)
        results = mem.search_memories(
            query_embedding=[1.0, 0.0],
            limit=5,
            cooldown_seconds=900,
        )
        assert results == []

    def test_search_includes_after_cooldown_expires(self, mem):
        mid = mem.save_memory(
            content="Used long ago",
            embedding=[1.0, 0.0],
            importance=0.8,
            source="test",
        )
        # Manually set last_used_at to 2 hours ago (well past cooldown)
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        with sqlite3.connect(mem.db_path) as conn:
            conn.execute(
                "UPDATE memories SET last_used_at = ? WHERE id = ?",
                (old_ts, mid),
            )
            conn.commit()

        results = mem.search_memories(
            query_embedding=[1.0, 0.0],
            limit=5,
            cooldown_seconds=900,
        )
        assert len(results) == 1
        assert results[0]["id"] == mid

    def test_never_used_not_filtered_by_cooldown(self, mem):
        mem.save_memory(
            content="Never used memory",
            embedding=[1.0, 0.0],
            importance=0.5,
            source="test",
        )
        results = mem.search_memories(
            query_embedding=[1.0, 0.0],
            limit=5,
            cooldown_seconds=900,
        )
        assert len(results) == 1


# ── save_or_update (near-duplicate detection) ─────────────────────────


class TestUpdateNearDuplicate:
    def test_update_near_duplicate(self, mem):
        emb = [1.0, 0.0, 0.0]
        mem.save_memory(
            content="Alice likes hiking in the mountains",
            embedding=emb,
            importance=0.7,
            source="chat",
        )
        # Same embedding = similarity 1.0, above default threshold 0.85
        status = mem.save_or_update(
            content="Alice loves hiking in the mountains",
            embedding=emb,
            importance=0.8,
            source="chat",
            duplicate_threshold=0.85,
        )
        assert status == "updated"

        # Should still be only 1 active memory
        with sqlite3.connect(mem.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE is_active = 1"
            ).fetchone()[0]
        assert count == 1

        # Content should be updated
        results = mem.search_memories(query_embedding=emb, limit=5)
        assert results[0]["content"] == "Alice loves hiking in the mountains"

    def test_save_or_update_adds_new_when_no_duplicate(self, mem):
        emb_a = [1.0, 0.0, 0.0]
        emb_b = [0.0, 1.0, 0.0]

        mem.save_memory(
            content="Alice likes hiking",
            embedding=emb_a,
            importance=0.7,
            source="chat",
        )
        status = mem.save_or_update(
            content="Bob likes cooking",
            embedding=emb_b,
            importance=0.6,
            source="chat",
            duplicate_threshold=0.85,
        )
        assert status == "inserted"

        with sqlite3.connect(mem.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM memories WHERE is_active = 1"
            ).fetchone()[0]
        assert count == 2

    def test_save_or_update_respects_threshold(self, mem):
        """With a very high threshold, even similar items get inserted."""
        emb_a = [1.0, 0.0, 0.0]
        emb_b = [0.95, 0.31, 0.0]  # similarity ~ 0.95

        mem.save_memory(content="Fact A", embedding=emb_a, importance=0.5, source=None)
        status = mem.save_or_update(
            content="Fact B",
            embedding=emb_b,
            importance=0.5,
            source=None,
            duplicate_threshold=0.99,
        )
        assert status == "inserted"


# ── mark_used ──────────────────────────────────────────────────────────


class TestMarkUsed:
    def test_mark_used_updates_count_and_timestamp(self, mem):
        mid = mem.save_memory(
            content="Something useful",
            embedding=[1.0, 0.0],
            importance=0.5,
            source="test",
        )
        mem.mark_used([mid])

        with sqlite3.connect(mem.db_path) as conn:
            row = conn.execute(
                "SELECT use_count, last_used_at FROM memories WHERE id = ?",
                (mid,),
            ).fetchone()
        assert row[0] == 1
        assert row[1] is not None

    def test_mark_used_increments(self, mem):
        mid = mem.save_memory(
            content="Reused memory",
            embedding=[1.0, 0.0],
            importance=0.5,
            source="test",
        )
        mem.mark_used([mid])
        mem.mark_used([mid])
        mem.mark_used([mid])

        with sqlite3.connect(mem.db_path) as conn:
            count = conn.execute(
                "SELECT use_count FROM memories WHERE id = ?", (mid,)
            ).fetchone()[0]
        assert count == 3

    def test_mark_used_empty_list(self, mem):
        # Should not raise
        mem.mark_used([])


# ── deactivate ─────────────────────────────────────────────────────────


class TestDeactivate:
    def test_deactivate(self, mem):
        mid = mem.save_memory(
            content="To be deactivated",
            embedding=[1.0, 0.0],
            importance=0.5,
            source="test",
        )
        mem.deactivate(mid)

        with sqlite3.connect(mem.db_path) as conn:
            row = conn.execute(
                "SELECT is_active FROM memories WHERE id = ?", (mid,)
            ).fetchone()
        assert row[0] == 0

    def test_deactivate_excludes_from_search(self, mem):
        mid = mem.save_memory(
            content="Deactivated memory",
            embedding=[1.0, 0.0],
            importance=0.9,
            source="test",
        )
        mem.deactivate(mid)
        results = mem.search_memories(query_embedding=[1.0, 0.0], limit=5)
        assert results == []


# ── Scoring and ranking ───────────────────────────────────────────────


class TestScoringAndRanking:
    def test_recency_affects_ranking(self, mem):
        """A recent memory with similar embedding should rank higher than an
        old memory, all else being equal."""
        emb = [1.0, 0.0]

        id_old = mem.save_memory(
            content="Old memory",
            embedding=emb,
            importance=0.5,
            source="test",
        )
        id_new = mem.save_memory(
            content="New memory",
            embedding=emb,
            importance=0.5,
            source="test",
        )

        # Make the first memory 60 days old
        old_ts = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        with sqlite3.connect(mem.db_path) as conn:
            conn.execute(
                "UPDATE memories SET updated_at = ? WHERE id = ?",
                (old_ts, id_old),
            )
            conn.commit()

        results = mem.search_memories(query_embedding=emb, limit=5)
        assert len(results) == 2
        assert results[0]["content"] == "New memory"
        assert results[1]["content"] == "Old memory"
        # New memory should have higher score
        assert results[0]["score"] > results[1]["score"]

    def test_importance_affects_ranking(self, mem):
        """Higher importance should boost ranking when semantic similarity
        is equal."""
        emb = [1.0, 0.0]

        mem.save_memory(
            content="Low importance",
            embedding=emb,
            importance=0.1,
            source="test",
        )
        mem.save_memory(
            content="High importance",
            embedding=emb,
            importance=0.95,
            source="test",
        )

        results = mem.search_memories(query_embedding=emb, limit=5)
        assert results[0]["content"] == "High importance"
        assert results[0]["score"] > results[1]["score"]
