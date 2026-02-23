import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, Message, User, Chat, CallbackQuery
from telegram.ext import ContextTypes


def make_update(
    text: str = "/memory",
    chat_id: int = 1,
    first_name: str = "Alice",
    user_id: int = 10,
    chat_type: str = "private",
    callback_data: str | None = None,
) -> Update:
    user = MagicMock(spec=User)
    user.first_name = first_name
    user.username = first_name.lower()
    user.id = user_id

    chat = MagicMock(spec=Chat)
    chat.id = chat_id
    chat.type = chat_type

    message = MagicMock(spec=Message)
    message.text = text
    message.chat_id = chat_id
    message.from_user = user
    message.chat = chat
    message.reply_text = AsyncMock()

    update = MagicMock(spec=Update)
    update.message = message
    update.effective_chat = chat
    update.effective_user = user

    if callback_data is not None:
        query = MagicMock(spec=CallbackQuery)
        query.data = callback_data
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()
        query.from_user = user
        query.message = message
        update.callback_query = query
        # For callback queries, update.message usually contains the bot's message
        # but update.effective_user is the user who clicked. The test structure works.
    else:
        update.callback_query = None

    return update


def make_context(args: list[str] | None = None) -> ContextTypes.DEFAULT_TYPE:
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.args = args or []
    return context


@pytest.mark.asyncio
async def test_memory_command_shows_facts():
    from bot.memory_handlers import handle_memory_command

    update = make_update()
    context = make_context()

    with patch("bot.memory_handlers.ALLOWED_CHAT_IDS", {1}):
        with patch("bot.memory_handlers.user_memory") as mock_memory:
            mock_memory.get_user_facts_page.return_value = (
                [{"id": 42, "fact_text": "Alice likes testing"}],
                1,
            )
            await handle_memory_command(update, context)

    update.message.reply_text.assert_called_once()
    args, kwargs = update.message.reply_text.call_args
    assert "Memories" in args[0]
    keyboard = kwargs.get("reply_markup")
    assert keyboard is not None
    # Check button data
    assert keyboard.inline_keyboard[0][0].callback_data == "mem:view:42:10"


@pytest.mark.asyncio
async def test_memory_command_no_facts():
    from bot.memory_handlers import handle_memory_command

    update = make_update()
    context = make_context()

    with patch("bot.memory_handlers.ALLOWED_CHAT_IDS", {1}):
        with patch("bot.memory_handlers.user_memory") as mock_memory:
            mock_memory.get_user_facts_page.return_value = ([], 0)
            await handle_memory_command(update, context)

    update.message.reply_text.assert_called_once()
    args, kwargs = update.message.reply_text.call_args
    assert "No memories stored" in args[0]
    assert "reply_markup" not in kwargs


@pytest.mark.asyncio
async def test_memory_command_private_chat_user_id_override():
    from bot.memory_handlers import handle_memory_command

    # Admin Alice (10) checks memories of Bob (20)
    update = make_update(chat_type="private")
    context = make_context(args=["20"])

    with patch("bot.memory_handlers.ALLOWED_CHAT_IDS", {1}):
        with patch("bot.memory_handlers.user_memory") as mock_memory:
            mock_memory.get_user_facts_page.return_value = ([], 0)
            await handle_memory_command(update, context)

    mock_memory.get_user_facts_page.assert_called_once_with(20, page=0)


@pytest.mark.asyncio
async def test_memory_command_group_chat_blocked():
    from bot.memory_handlers import handle_memory_command

    # Alice (10) checks memories in group chat
    update = make_update(chat_type="supergroup", chat_id=200)
    context = make_context()

    with patch("bot.memory_handlers.ALLOWED_CHAT_IDS", {200}):
        with patch("bot.memory_handlers.user_memory") as mock_memory:
            await handle_memory_command(update, context)

    # Should block and ask to use direct messages
    mock_memory.get_user_facts_page.assert_not_called()
    update.message.reply_text.assert_called_once()
    args, _ = update.message.reply_text.call_args
    assert "privacy" in args[0].lower()
    assert "direct messages" in args[0].lower()


@pytest.mark.asyncio
async def test_memory_callback_delete():
    from bot.memory_handlers import handle_memory_callback

    update = make_update(callback_data="mem:del:42:10")
    context = make_context()

    with patch("bot.memory_handlers.user_memory") as mock_memory:
        mock_memory.delete_fact.return_value = True
        # For the refresh part
        mock_memory.get_user_facts_page.return_value = ([], 0)
        
        await handle_memory_callback(update, context)

    update.callback_query.answer.assert_called_once()
    mock_memory.delete_fact.assert_called_once_with(fact_id=42, user_id=10)
    
    update.callback_query.edit_message_text.assert_called_once()
    args, _ = update.callback_query.edit_message_text.call_args
    assert "Deleted" in args[0]


@pytest.mark.asyncio
async def test_memory_callback_view():
    from bot.memory_handlers import handle_memory_callback

    update = make_update(callback_data="mem:view:42:10")
    context = make_context()

    with patch("bot.memory_handlers.user_memory") as mock_memory:
        mock_memory.get_user_facts_page.return_value = (
            [{"id": 42, "fact_text": "Alice is typing"}],
            1,
        )
        await handle_memory_callback(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    args, kwargs = update.callback_query.edit_message_text.call_args
    assert "Alice is typing" in args[0]
    keyboard = kwargs.get("reply_markup")
    assert keyboard is not None
    # 2 rows: (Edit, Delete) and (Back)
    assert len(keyboard.inline_keyboard) == 2


@pytest.mark.asyncio
async def test_memory_edit_flow():
    from bot.memory_handlers import (
        handle_memory_callback,
        handle_memory_edit_reply,
        _pending_edits,
    )
    
    _pending_edits.clear()

    # 1. User taps Edit
    update_cb = make_update(callback_data="mem:edit:42:10", chat_id=1, user_id=10)
    context = make_context()
    await handle_memory_callback(update_cb, context)
    
    # State should be saved: (1, 10) -> (42, 10)
    assert _pending_edits[(1, 10)] == (42, 10)
    update_cb.callback_query.edit_message_text.assert_called_once()
    
    # 2. User sends reply text
    update_msg = make_update(text="New modified fact", chat_id=1, user_id=10)
    
    with patch("bot.memory_handlers.user_memory") as mock_memory:
        mock_memory.update_fact_text.return_value = True
        
        # Dispatcher calls handle_memory_edit_reply
        consumed = await handle_memory_edit_reply(update_msg, context)
        
        assert consumed is True
        mock_memory.update_fact_text.assert_called_once_with(
            fact_id=42, user_id=10, new_text="New modified fact"
        )
        update_msg.message.reply_text.assert_called_once()
        args, _ = update_msg.message.reply_text.call_args
        assert "updated" in args[0].lower()
    
    # State should be cleared
    assert (1, 10) not in _pending_edits


@pytest.mark.asyncio
async def test_memory_edit_flow_ignores_normal_messages():
    from bot.memory_handlers import handle_memory_edit_reply, _pending_edits
    _pending_edits.clear()
    
    update = make_update(text="Just chatting", chat_id=1, user_id=10)
    context = make_context()
    
    # No pending edit for this user
    consumed = await handle_memory_edit_reply(update, context)
    assert consumed is False
    update.message.reply_text.assert_not_called()
