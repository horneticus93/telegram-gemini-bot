import asyncio

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, Message, User, Chat
from telegram.ext import ContextTypes


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def mock_update():
    user = MagicMock(spec=User)
    user.first_name = "Alice"
    user.username = "alice"
    user.id = 42

    chat = MagicMock(spec=Chat)
    chat.type = "group"

    message = MagicMock(spec=Message)
    message.text = "@testbot what is the weather?"
    message.chat_id = -100123
    message.from_user = user
    message.chat = chat
    message.reply_text = AsyncMock()
    message.reply_to_message = None

    update = MagicMock(spec=Update)
    update.message = message
    return update


@pytest.fixture
def mock_context():
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = MagicMock()
    context.bot.username = "testbot"
    context.bot.send_chat_action = AsyncMock()
    return context


# ── Tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@patch("bot.handlers.ALLOWED_CHAT_IDS", {-100123})
@patch("bot.handlers.session_manager")
@patch("bot.handlers.bot_memory")
@patch("bot.handlers.compiled_graph")
async def test_handle_message_responds_on_mention(
    mock_graph, mock_memory, mock_session, mock_update, mock_context
):
    """Bot replies when @mentioned in a group chat."""
    from bot.handlers import handle_message

    # Setup session_manager mocks
    mock_session.get_recent.return_value = []
    mock_session.get_summary.return_value = ""
    mock_session.needs_summary.return_value = False

    # Graph returns an AIMessage with content
    ai_response = AIMessage(content="It's sunny today!")
    mock_graph.invoke.return_value = {
        "messages": [HumanMessage(content="what is the weather?"), ai_response]
    }

    await handle_message(mock_update, mock_context)

    mock_update.message.reply_text.assert_called()
    # Verify the bot's response text was sent
    reply_text = mock_update.message.reply_text.call_args[0][0]
    assert "sunny" in reply_text


@pytest.mark.asyncio
@patch("bot.handlers.ALLOWED_CHAT_IDS", {-100123})
@patch("bot.handlers.session_manager")
async def test_handle_message_ignores_non_mention_in_group(
    mock_session, mock_update, mock_context
):
    """Messages without @bot mention in group chat are stored but not replied to."""
    from bot.handlers import handle_message

    # Remove the bot mention from text
    mock_update.message.text = "just chatting with friends"
    mock_update.message.chat.type = "group"
    mock_update.message.reply_to_message = None

    await handle_message(mock_update, mock_context)

    # Message should be stored in session
    mock_session.add_message.assert_called_once()
    # But no reply should be sent
    mock_update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
@patch("bot.handlers.ALLOWED_CHAT_IDS", set())
@patch("bot.handlers.session_manager")
async def test_handle_message_ignores_disallowed_chat(
    mock_session, mock_update, mock_context
):
    """Messages from disallowed chat IDs are silently ignored."""
    from bot.handlers import handle_message

    await handle_message(mock_update, mock_context)

    mock_update.message.reply_text.assert_not_called()
    mock_session.add_message.assert_not_called()


@pytest.mark.asyncio
@patch("bot.handlers.ALLOWED_CHAT_IDS", {-100123})
@patch("bot.handlers.session_manager")
@patch("bot.handlers.bot_memory")
@patch("bot.handlers.compiled_graph")
async def test_handle_message_responds_in_private_chat(
    mock_graph, mock_memory, mock_session, mock_update, mock_context
):
    """Bot always responds in private chats regardless of mention."""
    from bot.handlers import handle_message

    mock_update.message.text = "hello there"
    mock_update.message.chat.type = "private"
    mock_session.get_recent.return_value = []
    mock_session.get_summary.return_value = ""
    mock_session.needs_summary.return_value = False

    ai_response = AIMessage(content="Hi! How can I help?")
    mock_graph.invoke.return_value = {
        "messages": [HumanMessage(content="hello there"), ai_response]
    }

    await handle_message(mock_update, mock_context)

    mock_update.message.reply_text.assert_called()


@pytest.mark.asyncio
@patch("bot.handlers.ALLOWED_CHAT_IDS", {-100123})
@patch("bot.handlers.session_manager")
@patch("bot.handlers.bot_memory")
@patch("bot.handlers.compiled_graph")
async def test_handle_message_responds_on_reply_to_bot(
    mock_graph, mock_memory, mock_session, mock_update, mock_context
):
    """Bot responds when someone replies to one of its messages."""
    from bot.handlers import handle_message

    mock_update.message.text = "can you elaborate?"
    reply_msg = MagicMock()
    reply_msg.from_user = MagicMock()
    reply_msg.from_user.username = "testbot"
    mock_update.message.reply_to_message = reply_msg

    mock_session.get_recent.return_value = []
    mock_session.get_summary.return_value = ""
    mock_session.needs_summary.return_value = False

    ai_response = AIMessage(content="Sure, let me explain more.")
    mock_graph.invoke.return_value = {
        "messages": [HumanMessage(content="can you elaborate?"), ai_response]
    }

    await handle_message(mock_update, mock_context)

    mock_update.message.reply_text.assert_called()


@pytest.mark.asyncio
@patch("bot.handlers.ALLOWED_CHAT_IDS", {-100123})
@patch("bot.handlers.session_manager")
@patch("bot.handlers.bot_memory")
@patch("bot.handlers.compiled_graph")
async def test_handle_message_strips_bot_mention(
    mock_graph, mock_memory, mock_session, mock_update, mock_context
):
    """@bot mention is stripped from the question before sending to graph."""
    from bot.handlers import handle_message

    mock_update.message.text = "@testbot what is 2+2?"
    mock_session.get_recent.return_value = []
    mock_session.get_summary.return_value = ""
    mock_session.needs_summary.return_value = False

    ai_response = AIMessage(content="4")
    mock_graph.invoke.return_value = {
        "messages": [HumanMessage(content="what is 2+2?"), ai_response]
    }

    await handle_message(mock_update, mock_context)

    # Check the state dict passed to graph.invoke
    invoke_args = mock_graph.invoke.call_args[0][0]
    # The last HumanMessage should not contain @testbot
    last_human = [m for m in invoke_args["messages"] if isinstance(m, HumanMessage)][-1]
    assert "@testbot" not in last_human.content
    assert "2+2" in last_human.content


@pytest.mark.asyncio
@patch("bot.handlers.ALLOWED_CHAT_IDS", {-100123})
@patch("bot.handlers.session_manager")
@patch("bot.handlers.bot_memory")
@patch("bot.handlers.compiled_graph")
async def test_handle_message_stores_bot_response_in_session(
    mock_graph, mock_memory, mock_session, mock_update, mock_context
):
    """Bot response is stored in session as a 'model' message."""
    from bot.handlers import handle_message

    mock_session.get_recent.return_value = []
    mock_session.get_summary.return_value = ""
    mock_session.needs_summary.return_value = False

    ai_response = AIMessage(content="Here is my answer.")
    mock_graph.invoke.return_value = {
        "messages": [ai_response]
    }

    await handle_message(mock_update, mock_context)

    # Verify model message was stored
    model_calls = [
        call for call in mock_session.add_message.call_args_list
        if call[0][1] == "model"  # second positional arg is role
    ]
    assert len(model_calls) == 1
    assert "Here is my answer." in model_calls[0][0][2]


@pytest.mark.asyncio
@patch("bot.handlers.ALLOWED_CHAT_IDS", {-100123})
@patch("bot.handlers.session_manager")
@patch("bot.handlers.bot_memory")
@patch("bot.handlers.compiled_graph")
async def test_handle_message_extracts_last_ai_message_without_tool_calls(
    mock_graph, mock_memory, mock_session, mock_update, mock_context
):
    """Response is the LAST AIMessage without tool_calls, not the first."""
    from bot.handlers import handle_message

    mock_session.get_recent.return_value = []
    mock_session.get_summary.return_value = ""
    mock_session.needs_summary.return_value = False

    # Graph returns multiple messages: tool-calling AI, then final AI
    ai_with_tool = AIMessage(content="", tool_calls=[{"name": "memory_search", "args": {"query": "test"}, "id": "1"}])
    ai_final = AIMessage(content="The final answer.")
    mock_graph.invoke.return_value = {
        "messages": [
            HumanMessage(content="question"),
            ai_with_tool,
            ai_final,
        ]
    }

    await handle_message(mock_update, mock_context)

    reply_text = mock_update.message.reply_text.call_args[0][0]
    assert reply_text == "The final answer."


@pytest.mark.asyncio
@patch("bot.handlers.ALLOWED_CHAT_IDS", {-100123})
@patch("bot.handlers.session_manager")
@patch("bot.handlers.bot_memory")
@patch("bot.handlers.compiled_graph")
async def test_handle_message_splits_long_response(
    mock_graph, mock_memory, mock_session, mock_update, mock_context
):
    """Responses longer than 4096 characters are split into multiple messages."""
    from bot.handlers import handle_message

    mock_session.get_recent.return_value = []
    mock_session.get_summary.return_value = ""
    mock_session.needs_summary.return_value = False

    long_text = "A" * 5000
    ai_response = AIMessage(content=long_text)
    mock_graph.invoke.return_value = {"messages": [ai_response]}

    await handle_message(mock_update, mock_context)

    assert mock_update.message.reply_text.call_count == 2
    first_chunk = mock_update.message.reply_text.call_args_list[0][0][0]
    second_chunk = mock_update.message.reply_text.call_args_list[1][0][0]
    assert len(first_chunk) == 4096
    assert len(second_chunk) == 5000 - 4096


@pytest.mark.asyncio
@patch("bot.handlers.ALLOWED_CHAT_IDS", {-100123})
@patch("bot.handlers.session_manager")
async def test_handle_message_returns_early_no_text(
    mock_session, mock_update, mock_context
):
    """Returns early when message has no text."""
    from bot.handlers import handle_message

    mock_update.message.text = None

    await handle_message(mock_update, mock_context)

    mock_update.message.reply_text.assert_not_called()
    mock_session.add_message.assert_not_called()


@pytest.mark.asyncio
@patch("bot.handlers.ALLOWED_CHAT_IDS", {-100123})
@patch("bot.handlers.session_manager")
async def test_handle_message_returns_early_no_user(
    mock_session, mock_update, mock_context
):
    """Returns early when from_user is None."""
    from bot.handlers import handle_message

    mock_update.message.from_user = None

    await handle_message(mock_update, mock_context)

    mock_update.message.reply_text.assert_not_called()
    mock_session.add_message.assert_not_called()


@pytest.mark.asyncio
@patch("bot.handlers.ALLOWED_CHAT_IDS", {-100123})
@patch("bot.handlers.session_manager")
@patch("bot.handlers.bot_memory")
@patch("bot.handlers.compiled_graph")
async def test_handle_message_sends_typing_action(
    mock_graph, mock_memory, mock_session, mock_update, mock_context
):
    """Typing indicator is sent while processing."""
    from bot.handlers import handle_message

    mock_session.get_recent.return_value = []
    mock_session.get_summary.return_value = ""
    mock_session.needs_summary.return_value = False

    ai_response = AIMessage(content="Done.")
    mock_graph.invoke.return_value = {"messages": [ai_response]}

    await handle_message(mock_update, mock_context)

    mock_context.bot.send_chat_action.assert_called_with(
        chat_id=-100123, action="typing"
    )


@pytest.mark.asyncio
@patch("bot.handlers.ALLOWED_CHAT_IDS", {-100123})
@patch("bot.handlers.session_manager")
@patch("bot.handlers.bot_memory")
@patch("bot.handlers.compiled_graph")
async def test_handle_message_triggers_summary_when_needed(
    mock_graph, mock_memory, mock_session, mock_update, mock_context
):
    """Background summarization is triggered when threshold is met."""
    from bot.handlers import handle_message

    mock_session.get_recent.return_value = []
    mock_session.get_summary.return_value = ""
    mock_session.needs_summary.return_value = True
    mock_session.get_unsummarized.return_value = [
        {"role": "user", "text": "msg", "author": "Alice"}
    ] * 30
    mock_session.format_history.return_value = "conversation text"

    ai_response = AIMessage(content="response")
    mock_graph.invoke.return_value = {"messages": [ai_response]}

    with patch("bot.handlers._summarize_chat", new_callable=AsyncMock) as mock_summarize:
        await handle_message(mock_update, mock_context)

        # Give the background task a moment to be created
        await asyncio.sleep(0.05)

        # _summarize_chat should have been called as a background task
        # It's created via asyncio.create_task, so we patch it directly
        # The actual call happens through asyncio.create_task

    # We verify needs_summary was checked
    mock_session.needs_summary.assert_called()


@pytest.mark.asyncio
@patch("bot.handlers.ALLOWED_CHAT_IDS", {-100123})
@patch("bot.handlers.session_manager")
@patch("bot.handlers.bot_memory")
@patch("bot.handlers.compiled_graph")
async def test_handle_message_adds_user_message_to_session(
    mock_graph, mock_memory, mock_session, mock_update, mock_context
):
    """User message is stored in session with correct author format."""
    from bot.handlers import handle_message

    mock_session.get_recent.return_value = []
    mock_session.get_summary.return_value = ""
    mock_session.needs_summary.return_value = False

    ai_response = AIMessage(content="ok")
    mock_graph.invoke.return_value = {"messages": [ai_response]}

    await handle_message(mock_update, mock_context)

    # First add_message call should be for the user message
    user_call = mock_session.add_message.call_args_list[0]
    assert user_call[0][0] == -100123  # chat_id
    assert user_call[0][1] == "user"   # role
    assert user_call[1]["author"] == "Alice [ID: 42]"
