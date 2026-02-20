import pytest
from bot.session import SessionManager


def test_add_and_get_single_message():
    sm = SessionManager(max_messages=10)
    sm.add_message(chat_id=1, role="user", text="Hello")
    assert sm.get_history(1) == [{"role": "user", "text": "Hello"}]


def test_empty_history_for_unknown_chat():
    sm = SessionManager(max_messages=10)
    assert sm.get_history(999) == []


def test_rolling_window_drops_oldest():
    sm = SessionManager(max_messages=3)
    sm.add_message(1, "user", "msg1")
    sm.add_message(1, "model", "msg2")
    sm.add_message(1, "user", "msg3")
    sm.add_message(1, "model", "msg4")  # should push out msg1
    history = sm.get_history(1)
    assert history == [
        {"role": "model", "text": "msg2"},
        {"role": "user", "text": "msg3"},
        {"role": "model", "text": "msg4"},
    ]


def test_rolling_window_preserves_order():
    sm = SessionManager(max_messages=3)
    sm.add_message(1, "user", "first")
    sm.add_message(1, "model", "second")
    sm.add_message(1, "user", "third")
    sm.add_message(1, "model", "fourth")  # evicts "first"
    history = sm.get_history(1)
    assert [e["text"] for e in history] == ["second", "third", "fourth"]


def test_format_history_joins_with_newlines():
    sm = SessionManager(max_messages=10)
    sm.add_message(1, "user", "Hi")
    sm.add_message(1, "model", "Hey")
    result = sm.format_history(1)
    assert result == "[user]: Hi\n[bot]: Hey"


def test_format_history_empty_chat():
    sm = SessionManager(max_messages=10)
    assert sm.format_history(999) == ""


def test_separate_chats_dont_mix():
    sm = SessionManager(max_messages=10)
    sm.add_message(1, "user", "chat1")
    sm.add_message(2, "user", "chat2")
    assert sm.get_history(1) == [{"role": "user", "text": "chat1"}]
    assert sm.get_history(2) == [{"role": "user", "text": "chat2"}]
