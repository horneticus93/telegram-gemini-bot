import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bot.handlers import should_respond


def make_update(is_private=False, bot_mentioned=False, reply_to_bot=False, chat_id=-100):
    update = MagicMock()
    update.message.chat.type = "private" if is_private else "group"
    update.message.chat_id = chat_id
    update.message.text = "@testbot hello" if bot_mentioned else "hello"
    update.message.reply_to_message = MagicMock(from_user=MagicMock(is_bot=True)) if reply_to_bot else None
    update.message.entities = []
    if bot_mentioned:
        ent = MagicMock()
        ent.type = "mention"
        update.message.entities = [ent]
    return update


def test_private_chat_always_responds():
    assert should_respond(make_update(is_private=True), bot_username="testbot", allowed_chat_ids={-100})

def test_group_responds_on_mention():
    assert should_respond(make_update(bot_mentioned=True), bot_username="testbot", allowed_chat_ids={-100})

def test_group_responds_on_reply_to_bot():
    assert should_respond(make_update(reply_to_bot=True), bot_username="testbot", allowed_chat_ids={-100})

def test_group_does_not_respond_without_mention():
    assert not should_respond(make_update(), bot_username="testbot", allowed_chat_ids={-100})

def test_not_in_allowed_chat_ids():
    assert not should_respond(make_update(is_private=True), bot_username="testbot", allowed_chat_ids={-999})
