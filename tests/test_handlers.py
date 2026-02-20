import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, Message, User, Chat
from telegram.ext import ContextTypes


def make_update(text: str, chat_id: int, first_name: str = "Alice") -> Update:
    user = MagicMock(spec=User)
    user.first_name = first_name
    user.username = first_name.lower()
    user.id = 0  # default integer id so SQLite binding works

    message = MagicMock(spec=Message)
    message.text = text
    message.chat_id = chat_id
    message.from_user = user
    message.reply_text = AsyncMock()

    update = MagicMock(spec=Update)
    update.message = message
    return update


def make_context(bot_username: str = "testbot") -> ContextTypes.DEFAULT_TYPE:
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = MagicMock()
    context.bot.username = bot_username
    return context


@pytest.mark.asyncio
async def test_ignores_disallowed_chat():
    from bot.handlers import handle_message
    update = make_update("hello", chat_id=9999)
    context = make_context()

    with patch("bot.handlers.ALLOWED_CHAT_IDS", {1}):
        await handle_message(update, context)

    update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_stores_message_without_tag():
    from bot.handlers import handle_message, session_manager
    update = make_update("just chatting", chat_id=1)
    context = make_context()

    with patch("bot.handlers.ALLOWED_CHAT_IDS", {1}):
        await handle_message(update, context)

    update.message.reply_text.assert_not_called()
    history = session_manager.get_history(1)
    assert any("just chatting" in msg["text"] for msg in history)


@pytest.mark.asyncio
async def test_replies_when_tagged():
    from bot.handlers import handle_message
    update = make_update("@testbot what time is it?", chat_id=2)
    context = make_context(bot_username="testbot")

    with patch("bot.handlers.ALLOWED_CHAT_IDS", {2}):
        with patch("bot.handlers.gemini_client") as mock_gemini:
            mock_gemini.ask.return_value = "It's noon!"
            await handle_message(update, context)

    update.message.reply_text.assert_called_once_with("It's noon!")


@pytest.mark.asyncio
async def test_replies_with_error_on_gemini_failure():
    from bot.handlers import handle_message
    update = make_update("@testbot crash?", chat_id=3)
    context = make_context(bot_username="testbot")

    with patch("bot.handlers.ALLOWED_CHAT_IDS", {3}):
        with patch("bot.handlers.gemini_client") as mock_gemini:
            mock_gemini.ask.side_effect = Exception("API error")
            await handle_message(update, context)

    update.message.reply_text.assert_called_once()
    args = update.message.reply_text.call_args[0][0]
    assert "wrong" in args.lower() or "error" in args.lower() or "sorry" in args.lower()


@pytest.mark.asyncio
async def test_strips_bot_mention_from_question():
    from bot.handlers import handle_message
    update = make_update("@testbot what is 2+2?", chat_id=4)
    context = make_context(bot_username="testbot")

    with patch("bot.handlers.ALLOWED_CHAT_IDS", {4}):
        with patch("bot.handlers.gemini_client") as mock_gemini:
            mock_gemini.ask.return_value = "4"
            await handle_message(update, context)

    call_kwargs = mock_gemini.ask.call_args.kwargs
    question = call_kwargs.get("question") or mock_gemini.ask.call_args.args[1]
    assert "@testbot" not in question
    assert "2+2" in question


@pytest.mark.asyncio
async def test_increments_user_message_count():
    from bot.handlers import handle_message, user_memory
    update = make_update("hello there", chat_id=10, first_name="TestUser")
    update.message.from_user.id = 42
    context = make_context()

    with patch("bot.handlers.ALLOWED_CHAT_IDS", {10}):
        await handle_message(update, context)

    profile = user_memory.get_profile(user_id=42)
    assert isinstance(profile, str)


@pytest.mark.asyncio
async def test_passes_user_profile_to_gemini():
    from bot.handlers import handle_message, user_memory
    user_memory.increment_message_count(99, 5, "bob", "Bob")  # create row first
    user_memory.update_profile(user_id=99, profile="Bob is a chef.")
    update = make_update("@testbot what should I cook?", chat_id=5, first_name="Bob")
    update.message.from_user.id = 99
    context = make_context(bot_username="testbot")

    with patch("bot.handlers.ALLOWED_CHAT_IDS", {5}):
        with patch("bot.handlers.gemini_client") as mock_gemini:
            mock_gemini.ask.return_value = "Try pasta!"
            await handle_message(update, context)

    call_kwargs = mock_gemini.ask.call_args.kwargs
    profile = call_kwargs.get("user_profile") or ""
    assert "Bob is a chef." in profile


@pytest.mark.asyncio
async def test_remember_keyword_triggers_immediate_profile_update():
    from bot.handlers import handle_message
    update = make_update("@testbot remember that I am a pilot", chat_id=6, first_name="Eve")
    update.message.from_user.id = 77
    context = make_context(bot_username="testbot")

    with patch("bot.handlers.ALLOWED_CHAT_IDS", {6}):
        with patch("bot.handlers.gemini_client") as mock_gemini:
            mock_gemini.ask.return_value = "Got it, I'll remember that!"
            mock_gemini.detect_remember_intent.return_value = True
            with patch("bot.handlers.user_memory") as mock_memory:
                mock_memory.increment_message_count.return_value = 1
                mock_memory.get_profile.return_value = ""
                mock_memory.get_chat_members.return_value = []
                with patch("bot.handlers._update_user_profile", new_callable=AsyncMock) as mock_update:
                    await handle_message(update, context)
                    mock_update.assert_awaited_once()
