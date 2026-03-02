import pytest
from bot.session import SessionManager


def test_add_and_get_history():
    """Adding messages stores them and get_history returns all in order."""
    sm = SessionManager(max_messages=50, recent_window=15)
    sm.add_message(1, "user", "Hello", author="Sasha")
    sm.add_message(1, "model", "Hi there")
    sm.add_message(1, "user", "How are you?", author="Sasha")

    history = sm.get_history(1)
    assert len(history) == 3
    assert history[0] == {"role": "user", "text": "Hello", "author": "Sasha"}
    assert history[1] == {"role": "model", "text": "Hi there", "author": None}
    assert history[2] == {"role": "user", "text": "How are you?", "author": "Sasha"}


def test_get_history_empty_chat():
    """get_history returns empty list for unknown chat."""
    sm = SessionManager()
    assert sm.get_history(999) == []


def test_add_message_respects_max_messages():
    """Deque rolls over when max_messages is exceeded."""
    sm = SessionManager(max_messages=3, recent_window=2)
    sm.add_message(1, "user", "msg1")
    sm.add_message(1, "model", "msg2")
    sm.add_message(1, "user", "msg3")
    sm.add_message(1, "model", "msg4")  # evicts msg1

    history = sm.get_history(1)
    assert len(history) == 3
    assert [m["text"] for m in history] == ["msg2", "msg3", "msg4"]


def test_separate_chats_dont_mix():
    """Messages from different chats are isolated."""
    sm = SessionManager()
    sm.add_message(1, "user", "chat1")
    sm.add_message(2, "user", "chat2")
    assert len(sm.get_history(1)) == 1
    assert len(sm.get_history(2)) == 1
    assert sm.get_history(1)[0]["text"] == "chat1"
    assert sm.get_history(2)[0]["text"] == "chat2"


def test_get_recent_returns_window():
    """get_recent returns at most recent_window messages from the end."""
    sm = SessionManager(max_messages=50, recent_window=3)
    for i in range(10):
        sm.add_message(1, "user", f"msg{i}")

    recent = sm.get_recent(1)
    assert len(recent) == 3
    assert [m["text"] for m in recent] == ["msg7", "msg8", "msg9"]


def test_get_recent_fewer_than_window():
    """get_recent returns all messages when fewer than recent_window exist."""
    sm = SessionManager(max_messages=50, recent_window=10)
    sm.add_message(1, "user", "only one")

    recent = sm.get_recent(1)
    assert len(recent) == 1
    assert recent[0]["text"] == "only one"


def test_get_recent_empty_chat():
    """get_recent returns empty list for unknown chat."""
    sm = SessionManager()
    assert sm.get_recent(999) == []


def test_get_unsummarized_messages():
    """get_unsummarized returns messages that haven't been summarized yet."""
    sm = SessionManager(max_messages=50, recent_window=15)
    for i in range(10):
        sm.add_message(1, "user", f"msg{i}")

    # Nothing summarized yet — all 10 are unsummarized
    unsummarized = sm.get_unsummarized(1)
    assert len(unsummarized) == 10

    # Mark first 5 as summarized
    sm.mark_summarized(1, 5)
    unsummarized = sm.get_unsummarized(1)
    assert len(unsummarized) == 5
    assert [m["text"] for m in unsummarized] == ["msg5", "msg6", "msg7", "msg8", "msg9"]


def test_get_unsummarized_empty_chat():
    """get_unsummarized returns empty list for unknown chat."""
    sm = SessionManager()
    assert sm.get_unsummarized(999) == []


def test_mark_summarized_cumulative():
    """mark_summarized is cumulative — calling it multiple times advances the pointer."""
    sm = SessionManager(max_messages=50, recent_window=15)
    for i in range(10):
        sm.add_message(1, "user", f"msg{i}")

    sm.mark_summarized(1, 3)
    assert len(sm.get_unsummarized(1)) == 7

    sm.mark_summarized(1, 4)
    assert len(sm.get_unsummarized(1)) == 3
    assert [m["text"] for m in sm.get_unsummarized(1)] == ["msg7", "msg8", "msg9"]


def test_summary_storage():
    """set_summary and get_summary store and retrieve running summary text."""
    sm = SessionManager()

    # No summary yet
    assert sm.get_summary(1) == ""

    sm.set_summary(1, "User discussed travel plans.")
    assert sm.get_summary(1) == "User discussed travel plans."

    # Overwrite
    sm.set_summary(1, "User discussed travel plans and food preferences.")
    assert sm.get_summary(1) == "User discussed travel plans and food preferences."


def test_summary_per_chat_isolation():
    """Summaries are isolated per chat."""
    sm = SessionManager()
    sm.set_summary(1, "Summary for chat 1")
    sm.set_summary(2, "Summary for chat 2")

    assert sm.get_summary(1) == "Summary for chat 1"
    assert sm.get_summary(2) == "Summary for chat 2"
    assert sm.get_summary(3) == ""


def test_needs_summary():
    """needs_summary returns True when unsummarized count meets threshold."""
    sm = SessionManager(max_messages=100, recent_window=15)

    # Empty chat — no summary needed
    assert sm.needs_summary(1, threshold=30) is False

    # Add 29 messages — not enough
    for i in range(29):
        sm.add_message(1, "user", f"msg{i}")
    assert sm.needs_summary(1, threshold=30) is False

    # Add 1 more — exactly 30
    sm.add_message(1, "user", "msg29")
    assert sm.needs_summary(1, threshold=30) is True

    # Mark some as summarized to drop below threshold
    sm.mark_summarized(1, 5)
    assert sm.needs_summary(1, threshold=30) is False  # 25 unsummarized


def test_needs_summary_default_threshold():
    """needs_summary uses default threshold of 30."""
    sm = SessionManager(max_messages=100, recent_window=15)
    for i in range(30):
        sm.add_message(1, "user", f"msg{i}")

    assert sm.needs_summary(1) is True


def test_format_history():
    """format_history produces flat text with author labels."""
    sm = SessionManager()
    sm.add_message(1, "user", "Hi there", author="Sasha")
    sm.add_message(1, "model", "Hello!")
    sm.add_message(1, "user", "What's up?", author="Ivan")

    result = sm.format_history(1)
    expected = "[Sasha]: Hi there\n[bot]: Hello!\n[Ivan]: What's up?"
    assert result == expected


def test_format_history_no_author():
    """format_history falls back to 'user' when author is None."""
    sm = SessionManager()
    sm.add_message(1, "user", "Anonymous message")
    sm.add_message(1, "model", "Bot reply")

    result = sm.format_history(1)
    assert result == "[user]: Anonymous message\n[bot]: Bot reply"


def test_format_history_empty_chat():
    """format_history returns empty string for unknown chat."""
    sm = SessionManager()
    assert sm.format_history(999) == ""
