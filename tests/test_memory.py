import pytest
from bot.memory import UserMemory
from alembic.config import Config
from alembic import command

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
    assert set(members) == {"Alice", "Bob"}
    assert "Carol" not in members


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
    assert results[0][0] == "Alice"
    assert results[1][0] == "Bob"

def test_search_profiles_by_embedding_empty_or_invalid(mem):
    # No profiles with embeddings yet
    assert mem.search_profiles_by_embedding([1.0, 0.0]) == []
    
    # Add profile without embedding
    mem.increment_message_count(1, 100, "alice", "Alice")
    mem.update_profile(1, "Alice is here", embedding=None)
    
    assert mem.search_profiles_by_embedding([1.0, 0.0]) == []
