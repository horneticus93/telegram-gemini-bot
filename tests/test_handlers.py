import asyncio
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
            mock_gemini.ask.return_value = ("It's noon!", False)
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
            mock_gemini.ask.return_value = ("4", False)
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
            mock_gemini.ask.return_value = ("Try pasta!", False)
            await handle_message(update, context)

    call_kwargs = mock_gemini.ask.call_args.kwargs
    profile = call_kwargs.get("user_profile") or ""
    assert "Bob is a chef." in profile


@pytest.mark.asyncio
async def test_save_to_profile_triggers_immediate_profile_update():
    """When the model sets save_to_profile=True, _update_user_profile is called."""
    from bot.handlers import handle_message
    update = make_update("@testbot remember that I am a pilot", chat_id=6, first_name="Eve")
    update.message.from_user.id = 77
    context = make_context(bot_username="testbot")

    with patch("bot.handlers.ALLOWED_CHAT_IDS", {6}):
        with patch("bot.handlers.gemini_client") as mock_gemini:
            mock_gemini.ask.return_value = ("Got it, I'll remember that!", True)
            with patch("bot.handlers.user_memory") as mock_memory:
                mock_memory.increment_message_count.return_value = 1
                mock_memory.get_profile.return_value = ""
                mock_memory.get_user_facts.return_value = []
                mock_memory.get_chat_members.return_value = []
                mock_memory.search_facts_by_embedding.return_value = []
                with patch("bot.handlers._update_user_profile", new_callable=AsyncMock) as mock_update:
                    await handle_message(update, context)
                    mock_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_no_profile_update_when_save_false():
    """When save_to_profile=False, _update_user_profile is NOT called eagerly."""
    from bot.handlers import handle_message
    update = make_update("@testbot what's 2+2?", chat_id=7, first_name="Alice")
    update.message.from_user.id = 88
    context = make_context(bot_username="testbot")

    with patch("bot.handlers.ALLOWED_CHAT_IDS", {7}):
        with patch("bot.handlers.gemini_client") as mock_gemini:
            mock_gemini.ask.return_value = ("4", False)
            with patch("bot.handlers.user_memory") as mock_memory:
                mock_memory.increment_message_count.return_value = 1
                mock_memory.get_profile.return_value = ""
                mock_memory.get_user_facts.return_value = []
                mock_memory.get_chat_members.return_value = []
                mock_memory.search_facts_by_embedding.return_value = []
                with patch("bot.handlers._update_user_profile", new_callable=AsyncMock) as mock_update:
                    await handle_message(update, context)
                    mock_update.assert_not_awaited()

@pytest.mark.asyncio
async def test_vector_search_rag_injection():
    """Verify that handle_message generates an embedding and performs fact-based search."""
    from bot.handlers import handle_message
    update = make_update("@testbot Who loves apples?", chat_id=8, first_name="Dave")
    update.message.from_user.id = 111
    context = make_context(bot_username="testbot")

    with patch("bot.handlers.ALLOWED_CHAT_IDS", {8}):
        with patch("bot.handlers.gemini_client") as mock_gemini:
            mock_gemini.ask.return_value = ("Alice does!", False)
            mock_gemini.embed_text.return_value = [0.1, 0.2, 0.3]
            with patch("bot.handlers.user_memory") as mock_memory:
                mock_memory.increment_message_count.return_value = 1
                mock_memory.get_profile.return_value = ""
                mock_memory.get_user_facts.return_value = []
                mock_memory.get_chat_members.return_value = [(1, "Alice")]
                mock_memory.search_facts_by_embedding.return_value = [
                    {
                        "fact_id": 10,
                        "scope": "user",
                        "user_id": 1,
                        "owner_name": "Alice",
                        "fact_text": "Alice loves apples",
                        "score": 0.88,
                    }
                ]
                
                await handle_message(update, context)
                
                # Verify embedding was generated for the question
                mock_gemini.embed_text.assert_called_once_with("Who loves apples?")
                
                # Verify fact search was performed with chat/user scope
                mock_memory.search_facts_by_embedding.assert_called_once_with(
                    query_embedding=[0.1, 0.2, 0.3],
                    chat_id=8,
                    asking_user_id=111,
                    limit=3,
                )
                
                # Verify retrieved facts were passed to ask()
                call_kwargs = mock_gemini.ask.call_args.kwargs
                retrieved = call_kwargs.get("retrieved_profiles")
                assert retrieved == ["[user fact] Alice [ID: 1]: Alice loves apples"]
                mock_memory.mark_facts_used.assert_called_once_with([10])


@pytest.mark.asyncio
async def test_memory_not_injected_when_no_relevant_facts():
    from bot.handlers import handle_message
    update = make_update("@testbot explain docker layers", chat_id=81, first_name="Sam")
    update.message.from_user.id = 812
    context = make_context(bot_username="testbot")

    with patch("bot.handlers.ALLOWED_CHAT_IDS", {81}):
        with patch("bot.handlers.gemini_client") as mock_gemini:
            mock_gemini.ask.return_value = ("Use smaller base images.", False)
            mock_gemini.embed_text.return_value = [0.4, 0.1, 0.5]
            with patch("bot.handlers.user_memory") as mock_memory:
                mock_memory.increment_message_count.return_value = 1
                mock_memory.get_profile.return_value = ""
                mock_memory.get_user_facts.return_value = []
                mock_memory.get_chat_members.return_value = [(812, "Sam")]
                mock_memory.search_facts_by_embedding.return_value = []

                await handle_message(update, context)

                call_kwargs = mock_gemini.ask.call_args.kwargs
                assert call_kwargs.get("retrieved_profiles") is None
                mock_memory.mark_facts_used.assert_not_called()


@pytest.mark.asyncio
async def test_date_extraction_runs_after_fact_upsert():
    """When facts are upserted, extract_date_from_fact is called for each."""
    from bot.handlers import handle_message

    ALLOWED_CHAT_ID = 500
    update = make_update("@testbot my birthday is March 10", chat_id=ALLOWED_CHAT_ID, first_name="Oleksandr")
    update.message.from_user.id = 200
    update.message.chat.type = "private"
    context = make_context(bot_username="testbot")

    with (
        patch("bot.handlers.gemini_client") as mock_gemini,
        patch("bot.handlers.user_memory") as mock_memory,
        patch("bot.handlers.session_manager"),
        patch("bot.handlers.ALLOWED_CHAT_IDS", {ALLOWED_CHAT_ID}),
        patch("bot.handlers.MEMORY_UPDATE_INTERVAL", 1),
    ):
        mock_memory.increment_message_count.return_value = 1
        mock_memory.get_profile.return_value = ""
        mock_memory.get_user_facts.return_value = []
        mock_memory.get_chat_members.return_value = []
        mock_memory.search_facts_by_embedding.return_value = []
        mock_memory.find_similar_facts.return_value = []

        mock_gemini.extract_facts.return_value = [
            {"fact": "Oleksandr's birthday is March 10", "importance": 0.9, "confidence": 0.9, "scope": "user"},
        ]
        mock_gemini.embed_text.return_value = [0.1] * 768
        mock_gemini.decide_fact_action.return_value = {"action": "keep_add_new", "target_fact_id": None}
        mock_gemini.extract_date_from_fact.return_value = {
            "event_type": "birthday", "event_date": "03-10", "title": "Oleksandr's birthday",
        }
        mock_gemini.ask.return_value = ("Got it!", False)

        await handle_message(update, context)
        # Wait for background task to complete
        await asyncio.sleep(0.1)

        mock_gemini.extract_date_from_fact.assert_called_once_with(
            "Oleksandr's birthday is March 10"
        )
        mock_memory.upsert_scheduled_event.assert_called_once()


@pytest.mark.asyncio
async def test_sends_typing_action():
    from bot.handlers import handle_message
    update = make_update("@testbot tell me a story", chat_id=123, first_name="Dave")
    context = make_context(bot_username="testbot")
    context.bot.send_chat_action = AsyncMock()

    with patch("bot.handlers.ALLOWED_CHAT_IDS", {123}):
        with patch("bot.handlers.gemini_client") as mock_gemini:
            mock_gemini.ask.return_value = ("Once upon a time...", False)
            
            # Use a side_effect that actually yields control
            original_sleep = asyncio.sleep
            async def fast_sleep(n):
                await original_sleep(0)

            with patch("bot.handlers.asyncio.sleep", side_effect=fast_sleep):
                await handle_message(update, context)

    # Verify typing action was sent
    context.bot.send_chat_action.assert_called_with(chat_id=123, action="typing")


@pytest.mark.asyncio
async def test_silence_timer_reset_called_on_message():
    """Each group message resets the silence timer."""
    from bot.handlers import handle_message

    ALLOWED_CHAT_ID = 600
    update = make_update("just chatting", chat_id=ALLOWED_CHAT_ID)
    update.message.chat.type = "group"
    context = make_context()

    with (
        patch("bot.handlers.gemini_client"),
        patch("bot.handlers.user_memory") as mock_memory,
        patch("bot.handlers.session_manager"),
        patch("bot.handlers.reset_silence_timer") as mock_reset,
        patch("bot.handlers.ALLOWED_CHAT_IDS", {ALLOWED_CHAT_ID}),
    ):
        mock_memory.increment_message_count.return_value = 1
        await handle_message(update, context)
        mock_reset.assert_called_once_with(context.job_queue, ALLOWED_CHAT_ID)
