import pytest
from bot.session import SessionManager


def test_add_and_get_single_message():
    sm = SessionManager(max_messages=10)
    sm.add_message(chat_id=1, author="Alice", text="Hello")
    assert sm.get_history(1) == ["[Alice]: Hello"]


def test_empty_history_for_unknown_chat():
    sm = SessionManager(max_messages=10)
    assert sm.get_history(999) == []


def test_rolling_window_drops_oldest():
    sm = SessionManager(max_messages=3)
    sm.add_message(1, "A", "msg1")
    sm.add_message(1, "A", "msg2")
    sm.add_message(1, "A", "msg3")
    sm.add_message(1, "A", "msg4")  # should push out msg1
    history = sm.get_history(1)
    assert len(history) == 3
    assert "[A]: msg1" not in history
    assert "[A]: msg4" in history


def test_format_history_joins_with_newlines():
    sm = SessionManager(max_messages=10)
    sm.add_message(1, "Alice", "Hi")
    sm.add_message(1, "Bob", "Hey")
    result = sm.format_history(1)
    assert result == "[Alice]: Hi\n[Bob]: Hey"


def test_format_history_empty_chat():
    sm = SessionManager(max_messages=10)
    assert sm.format_history(999) == ""


def test_separate_chats_dont_mix():
    sm = SessionManager(max_messages=10)
    sm.add_message(1, "Alice", "chat1")
    sm.add_message(2, "Bob", "chat2")
    assert sm.get_history(1) == ["[Alice]: chat1"]
    assert sm.get_history(2) == ["[Bob]: chat2"]
