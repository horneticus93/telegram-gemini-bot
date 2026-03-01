import pytest
from bot.memory import UserMemory
from alembic.config import Config
from alembic import command
from datetime import datetime, timedelta, timezone
import sqlite3

@pytest.fixture
def mem(tmp_path):
    db_path = str(tmp_path / "test.db")
    
    # Run alembic migrations specifically on this temporary DB
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(alembic_cfg, "head")
    
    return UserMemory(db_path=db_path)


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
    assert set(members) == {(1, "Alice"), (2, "Bob")}
    assert (3, "Carol") not in members


def test_get_chat_members_empty_chat_returns_empty(mem):
    assert mem.get_chat_members(chat_id=999) == []


def test_search_profiles_by_embedding(mem):
    mem.increment_message_count(1, 100, "alice", "Alice")
    mem.increment_message_count(2, 100, "bob", "Bob")
    mem.increment_message_count(3, 100, "charlie", "Charlie")
    
    # Vectors to simulate semantic meaning
    # Alice is [1.0, 0.0] -> matches query [0.9, 0.1]
    # Bob is [0.0, 1.0] -> orthogonal
    # Charlie is [-1.0, 0.0] -> opposite
    mem.update_profile(1, "Alice likes apples", embedding=[1.0, 0.0])
    mem.update_profile(2, "Bob likes bananas", embedding=[0.0, 1.0])
    mem.update_profile(3, "Charlie likes cats", embedding=[-1.0, 0.0])
    
    # Query somewhat similar to Alice
    results = mem.search_profiles_by_embedding([0.9, 0.1], limit=2)
    assert len(results) == 2
    assert results[0] == (1, "Alice", "Alice likes apples")
    assert results[1] == (2, "Bob", "Bob likes bananas")

def test_search_profiles_by_embedding_empty_or_invalid(mem):
    # No profiles with embeddings yet
    assert mem.search_profiles_by_embedding([1.0, 0.0]) == []


def test_upsert_user_facts_and_search_by_embedding(mem):
    mem.increment_message_count(1, 100, "alice", "Alice")
    mem.increment_message_count(2, 100, "bob", "Bob")
    mem.upsert_user_facts(
        user_id=1,
        chat_id=100,
        facts=[
            {
                "fact": "Alice prefers short concise answers.",
                "importance": 0.9,
                "confidence": 0.95,
                "embedding": [1.0, 0.0],
            }
        ],
    )
    mem.upsert_user_facts(
        user_id=2,
        chat_id=100,
        facts=[
            {
                "fact": "Bob likes long tutorials.",
                "importance": 0.2,
                "confidence": 0.8,
                "embedding": [0.0, 1.0],
            }
        ],
    )

    results = mem.search_facts_by_embedding(
        query_embedding=[0.95, 0.3], chat_id=100, asking_user_id=1, limit=3
    )

    assert len(results) == 2
    assert results[0]["fact_text"] == "Alice prefers short concise answers."
    assert results[0]["scope"] == "user"
    assert results[0]["owner_name"] == "Alice"
    assert "score" in results[0]


def test_search_facts_respects_cooldown(mem):
    mem.increment_message_count(1, 100, "alice", "Alice")
    mem.upsert_user_facts(
        user_id=1,
        chat_id=100,
        facts=[
            {
                "fact": "Alice wants gentle feedback style.",
                "importance": 0.8,
                "confidence": 0.9,
                "embedding": [1.0, 0.0],
            }
        ],
    )
    first = mem.search_facts_by_embedding(
        query_embedding=[1.0, 0.0], chat_id=100, asking_user_id=1, limit=3
    )
    assert len(first) == 1
    mem.mark_facts_used([first[0]["fact_id"]])

    second = mem.search_facts_by_embedding(
        query_embedding=[1.0, 0.0],
        chat_id=100,
        asking_user_id=1,
        limit=3,
        cooldown_seconds=3600,
    )
    assert second == []


def test_search_facts_uses_recency_and_importance(mem):
    mem.increment_message_count(1, 100, "alice", "Alice")
    mem.increment_message_count(2, 100, "bob", "Bob")
    mem.upsert_user_facts(
        user_id=1,
        chat_id=100,
        facts=[
            {
                "fact": "Alice likes practical examples.",
                "importance": 0.95,
                "confidence": 0.9,
                "embedding": [0.7, 0.7],
            }
        ],
    )
    mem.upsert_user_facts(
        user_id=2,
        chat_id=100,
        facts=[
            {
                "fact": "Bob likes abstract theory.",
                "importance": 0.2,
                "confidence": 0.9,
                "embedding": [0.72, 0.69],
            }
        ],
    )
    with sqlite3.connect(mem.db_path) as conn:
        old_ts = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        conn.execute(
            "UPDATE memory_facts SET updated_at = ? WHERE fact_text = ?",
            (old_ts, "Bob likes abstract theory."),
        )
        conn.commit()

    ranked = mem.search_facts_by_embedding(
        query_embedding=[0.71, 0.70], chat_id=100, asking_user_id=1, limit=2
    )
    assert [r["fact_text"] for r in ranked] == [
        "Alice likes practical examples.",
        "Bob likes abstract theory.",
    ]
    
    # Add profile without embedding
    mem.increment_message_count(1, 100, "alice", "Alice")
    mem.update_profile(1, "Alice is here", embedding=None)
    
    assert mem.search_profiles_by_embedding([1.0, 0.0]) == []


def test_find_similar_facts_returns_ranked_candidates(mem):
    mem.increment_message_count(1, 100, "alice", "Alice")
    mem.upsert_user_facts(
        user_id=1,
        chat_id=100,
        facts=[
            {
                "fact": "Alice plans to install 5 kW solar panels.",
                "importance": 0.9,
                "confidence": 0.9,
                "embedding": [1.0, 0.0],
            },
            {
                "fact": "Alice prefers concise replies.",
                "importance": 0.5,
                "confidence": 0.8,
                "embedding": [0.0, 1.0],
            },
        ],
    )
    similar = mem.find_similar_facts(
        scope="user",
        user_id=1,
        query_embedding=[0.95, 0.05],
        limit=2,
    )
    assert len(similar) == 1
    assert similar[0]["fact_text"] == "Alice plans to install 5 kW solar panels."


def test_upsert_user_facts_updates_target_fact_without_duplicate(mem):
    mem.increment_message_count(1, 100, "alice", "Alice")
    mem.upsert_user_facts(
        user_id=1,
        chat_id=100,
        facts=[
            {
                "fact": "Alice plans to install 5 kW solar panels.",
                "importance": 0.7,
                "confidence": 0.9,
                "embedding": [1.0, 0.0],
            }
        ],
    )
    with sqlite3.connect(mem.db_path) as conn:
        row = conn.execute(
            "SELECT id FROM memory_facts WHERE fact_text = ?",
            ("Alice plans to install 5 kW solar panels.",),
        ).fetchone()
        assert row is not None
        fact_id = row[0]

    mem.upsert_user_facts(
        user_id=1,
        chat_id=100,
        facts=[
            {
                "fact": "Alice plans to install around 2.5 kW solar panels.",
                "importance": 0.8,
                "confidence": 0.95,
                "embedding": [0.98, 0.02],
                "action": "update_existing",
                "target_fact_id": fact_id,
            }
        ],
    )
    facts = mem.get_user_facts(user_id=1, limit=10)
    assert "Alice plans to install around 2.5 kW solar panels." in facts
    assert "Alice plans to install 5 kW solar panels." not in facts
    with sqlite3.connect(mem.db_path) as conn:
        count = conn.execute(
            """
            SELECT COUNT(*) FROM memory_facts
            WHERE scope = 'user' AND user_id = ? AND is_active = 1
            """,
            (1,),
        ).fetchone()[0]
    assert count == 1


def test_upsert_user_facts_deactivates_target_fact(mem):
    mem.increment_message_count(1, 100, "alice", "Alice")
    mem.upsert_user_facts(
        user_id=1,
        chat_id=100,
        facts=[
            {
                "fact": "Alice wants to move next month.",
                "importance": 0.6,
                "confidence": 0.7,
                "embedding": [0.5, 0.5],
            }
        ],
    )
    with sqlite3.connect(mem.db_path) as conn:
        row = conn.execute(
            "SELECT id FROM memory_facts WHERE fact_text = ?",
            ("Alice wants to move next month.",),
        ).fetchone()
        assert row is not None
        fact_id = row[0]

    mem.upsert_user_facts(
        user_id=1,
        chat_id=100,
        facts=[
            {
                "fact": "Alice wants to move next month.",
                "action": "deactivate_existing",
                "target_fact_id": fact_id,
            }
        ],
    )
    assert mem.get_user_facts(user_id=1, limit=10) == []


def test_get_user_facts_page_returns_paginated_results(mem):
    mem.increment_message_count(1, 100, "alice", "Alice")
    # Insert 7 facts
    for i in range(7):
        mem.upsert_user_facts(
            user_id=1,
            chat_id=100,
            facts=[{"fact": f"Fact number {i}", "importance": 0.5, "confidence": 0.8}],
        )

    # Page 0 should have 5 facts (default page_size)
    facts_p0, total = mem.get_user_facts_page(user_id=1, page=0)
    assert total == 7
    assert len(facts_p0) == 5
    assert all("id" in f and "fact_text" in f for f in facts_p0)

    # Page 1 should have 2 facts
    facts_p1, total = mem.get_user_facts_page(user_id=1, page=1)
    assert total == 7
    assert len(facts_p1) == 2

    # Page 2 should be empty
    facts_p2, _ = mem.get_user_facts_page(user_id=1, page=2)
    assert facts_p2 == []

    # No overlap between pages
    ids_p0 = {f["id"] for f in facts_p0}
    ids_p1 = {f["id"] for f in facts_p1}
    assert ids_p0.isdisjoint(ids_p1)


def test_get_user_facts_page_empty_user(mem):
    facts, total = mem.get_user_facts_page(user_id=999, page=0)
    assert facts == []
    assert total == 0


def test_delete_fact_removes_fact(mem):
    mem.increment_message_count(1, 100, "alice", "Alice")
    mem.upsert_user_facts(
        user_id=1,
        chat_id=100,
        facts=[{"fact": "Alice likes tea", "importance": 0.5, "confidence": 0.8}],
    )
    facts, _ = mem.get_user_facts_page(user_id=1, page=0)
    assert len(facts) == 1
    fact_id = facts[0]["id"]

    result = mem.delete_fact(fact_id=fact_id, user_id=1)
    assert result is True

    facts_after, total = mem.get_user_facts_page(user_id=1, page=0)
    assert total == 0
    assert facts_after == []


def test_delete_fact_wrong_user_returns_false(mem):
    mem.increment_message_count(1, 100, "alice", "Alice")
    mem.increment_message_count(2, 100, "bob", "Bob")
    mem.upsert_user_facts(
        user_id=1,
        chat_id=100,
        facts=[{"fact": "Alice likes coffee", "importance": 0.5, "confidence": 0.8}],
    )
    facts, _ = mem.get_user_facts_page(user_id=1, page=0)
    fact_id = facts[0]["id"]

    # User 2 should not be able to delete user 1's fact
    result = mem.delete_fact(fact_id=fact_id, user_id=2)
    assert result is False

    # Fact should still exist
    facts_after, total = mem.get_user_facts_page(user_id=1, page=0)
    assert total == 1


def test_delete_fact_nonexistent_returns_false(mem):
    result = mem.delete_fact(fact_id=99999, user_id=1)
    assert result is False


def test_update_fact_text_changes_text_and_clears_embedding(mem):
    mem.increment_message_count(1, 100, "alice", "Alice")
    mem.upsert_user_facts(
        user_id=1,
        chat_id=100,
        facts=[
            {
                "fact": "Alice likes apples",
                "importance": 0.5,
                "confidence": 0.8,
                "embedding": [1.0, 0.0],
            }
        ],
    )
    facts, _ = mem.get_user_facts_page(user_id=1, page=0)
    fact_id = facts[0]["id"]

    result = mem.update_fact_text(fact_id=fact_id, user_id=1, new_text="Alice prefers oranges")
    assert result is True

    facts_after, _ = mem.get_user_facts_page(user_id=1, page=0)
    assert facts_after[0]["fact_text"] == "Alice prefers oranges"

    # Verify embedding was cleared
    with sqlite3.connect(mem.db_path) as conn:
        row = conn.execute(
            "SELECT embedding FROM memory_facts WHERE id = ?", (fact_id,)
        ).fetchone()
        assert row[0] is None


def test_update_fact_text_wrong_user_returns_false(mem):
    mem.increment_message_count(1, 100, "alice", "Alice")
    mem.upsert_user_facts(
        user_id=1,
        chat_id=100,
        facts=[{"fact": "Alice likes cats", "importance": 0.5, "confidence": 0.8}],
    )
    facts, _ = mem.get_user_facts_page(user_id=1, page=0)
    fact_id = facts[0]["id"]

    result = mem.update_fact_text(fact_id=fact_id, user_id=2, new_text="Hacked")
    assert result is False

    # Original text should remain
    facts_after, _ = mem.get_user_facts_page(user_id=1, page=0)
    assert facts_after[0]["fact_text"] == "Alice likes cats"


# --- scheduled_events CRUD tests ---


def test_upsert_scheduled_event_creates_new(mem):
    mem.upsert_scheduled_event(
        user_id=1,
        chat_id=100,
        event_type="birthday",
        event_date="03-15",
        title="Alice's birthday",
    )
    events = mem.get_events_for_date("03-15")
    assert len(events) == 1
    evt = events[0]
    assert evt["user_id"] == 1
    assert evt["chat_id"] == 100
    assert evt["event_type"] == "birthday"
    assert evt["event_date"] == "03-15"
    assert evt["title"] == "Alice's birthday"
    assert evt["source_fact_id"] is None
    assert evt["last_triggered"] is None
    assert evt["id"] is not None


def test_upsert_scheduled_event_updates_existing(mem):
    mem.upsert_scheduled_event(
        user_id=1,
        chat_id=100,
        event_type="birthday",
        event_date="03-15",
        title="Alice's birthday",
    )
    # Same (user_id, chat_id, event_type) but different date and title
    mem.upsert_scheduled_event(
        user_id=1,
        chat_id=100,
        event_type="birthday",
        event_date="04-20",
        title="Alice's birthday (corrected)",
    )
    # Old date should return nothing
    old_events = mem.get_events_for_date("03-15")
    assert len(old_events) == 0

    # New date should have the updated event
    new_events = mem.get_events_for_date("04-20")
    assert len(new_events) == 1
    assert new_events[0]["title"] == "Alice's birthday (corrected)"
    assert new_events[0]["event_date"] == "04-20"


def test_get_events_for_date_filters_inactive(mem):
    mem.upsert_scheduled_event(
        user_id=1,
        chat_id=100,
        event_type="birthday",
        event_date="06-01",
        title="Alice's birthday",
    )
    # Deactivate via raw SQL
    with sqlite3.connect(mem.db_path) as conn:
        conn.execute("UPDATE scheduled_events SET is_active = 0")
        conn.commit()

    events = mem.get_events_for_date("06-01")
    assert events == []


def test_get_events_for_date_groups_by_chat(mem):
    mem.upsert_scheduled_event(
        user_id=1, chat_id=100, event_type="birthday",
        event_date="07-04", title="Alice bday",
    )
    mem.upsert_scheduled_event(
        user_id=2, chat_id=100, event_type="birthday",
        event_date="07-04", title="Bob bday",
    )
    mem.upsert_scheduled_event(
        user_id=3, chat_id=200, event_type="birthday",
        event_date="07-04", title="Carol bday",
    )
    events = mem.get_events_for_date("07-04")
    assert len(events) == 3
    # Ordered by chat_id, event_type
    assert events[0]["chat_id"] == 100
    assert events[1]["chat_id"] == 100
    assert events[2]["chat_id"] == 200


def test_mark_event_triggered(mem):
    mem.upsert_scheduled_event(
        user_id=1, chat_id=100, event_type="anniversary",
        event_date="12-25", title="Xmas",
    )
    events = mem.get_events_for_date("12-25")
    assert events[0]["last_triggered"] is None

    mem.mark_event_triggered(events[0]["id"])

    events_after = mem.get_events_for_date("12-25")
    assert events_after[0]["last_triggered"] is not None
