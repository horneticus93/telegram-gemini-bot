import pytest
from unittest.mock import AsyncMock, MagicMock
from bot.context import ContextBuilder
from bot.processor import ProcessedMessage


def make_processed(text="hello", ctype="text"):
    return ProcessedMessage(
        text=text, image_bytes=None, content_type=ctype,
        author_name="Alice", author_id=1, chat_id=100, message_id=1,
    )


@pytest.mark.asyncio
async def test_builds_messages_with_history():
    session = MagicMock()
    session.get_recent.return_value = [
        {"role": "user", "text": "prev msg", "author": "Alice"},
    ]
    session.get_summary.return_value = None
    memory_search = AsyncMock(return_value=[])
    cb = ContextBuilder(session=session, memory_search=memory_search, settings=AsyncMock())
    messages = await cb.build(chat_id=100, processed=make_processed("new msg"))
    texts = [m["content"] for m in messages if isinstance(m["content"], str)]
    assert any("prev msg" in t for t in texts)
    assert any("new msg" in t for t in texts)


@pytest.mark.asyncio
async def test_includes_summary_when_present():
    session = MagicMock()
    session.get_recent.return_value = []
    session.get_summary.return_value = "Summary: user likes Python."
    memory_search = AsyncMock(return_value=[])
    cb = ContextBuilder(session=session, memory_search=memory_search, settings=AsyncMock())
    messages = await cb.build(chat_id=100, processed=make_processed("tell me more"))
    system_content = messages[0]["content"]
    assert "Summary" in system_content


@pytest.mark.asyncio
async def test_includes_memory_results():
    session = MagicMock()
    session.get_recent.return_value = []
    session.get_summary.return_value = None
    memory_search = AsyncMock(return_value=[{"name": "Oleh", "label": "Person"}])
    cb = ContextBuilder(session=session, memory_search=memory_search, settings=AsyncMock())
    messages = await cb.build(chat_id=100, processed=make_processed("who am I?"))
    system_content = messages[0]["content"]
    assert "Oleh" in system_content
