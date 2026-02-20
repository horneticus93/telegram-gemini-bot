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
