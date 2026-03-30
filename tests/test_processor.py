# tests/test_processor.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bot.processor import MessageProcessor, ProcessedMessage

def make_tg_message(text=None, photo=None, forward_from=None, entities=None):
    msg = MagicMock()
    msg.text = text
    msg.caption = None
    msg.photo = photo
    msg.forward_origin = forward_from  # forward_from is now a mock MessageOrigin
    msg.forward_from = None  # keep for backward compat with MagicMock
    msg.forward_from_chat = None
    msg.forward_date = None
    msg.entities = entities or []
    msg.from_user = MagicMock(id=1, username="testuser", full_name="Test User")
    msg.chat_id = -100123
    msg.message_id = 42
    return msg

@pytest.mark.asyncio
async def test_text_message():
    proc = MessageProcessor(settings=AsyncMock())
    msg = make_tg_message(text="Hello!")
    result = await proc.process(msg)
    assert result.content_type == "text"
    assert result.text == "Hello!"
    assert result.image_bytes is None

@pytest.mark.asyncio
async def test_url_in_text_fetches_content():
    proc = MessageProcessor(settings=AsyncMock())
    msg = make_tg_message(text="Check this: https://example.com")
    with patch("bot.processor.httpx.AsyncClient") as mock_client_cls:
        mock_response = MagicMock()
        mock_response.text = "<html><body>Example Domain</body></html>"
        mock_response.status_code = 200
        mock_client_instance = AsyncMock()
        mock_client_instance.get = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await proc.process(msg)
    assert result.content_type == "url"
    assert "Example Domain" in result.fetched_urls["https://example.com"]

@pytest.mark.asyncio
async def test_photo_message_downloads_bytes():
    settings = AsyncMock()
    proc = MessageProcessor(settings=settings)
    photo_size = MagicMock()
    photo_size.file_id = "abc123"
    msg = make_tg_message(photo=[photo_size])
    fake_bytes = b"\xff\xd8\xff"  # fake JPEG header
    mock_bot = AsyncMock()
    mock_bot.get_file = AsyncMock(return_value=AsyncMock(download_as_bytearray=AsyncMock(return_value=fake_bytes)))
    result = await proc.process(msg, bot=mock_bot)
    assert result.content_type == "photo"
    assert result.image_bytes == fake_bytes

@pytest.mark.asyncio
async def test_forward_message():
    proc = MessageProcessor(settings=AsyncMock())
    forward_origin = MagicMock()
    forward_origin.sender_user_name = "Alice"
    msg = make_tg_message(text="forwarded text")
    msg.forward_origin = forward_origin
    result = await proc.process(msg)
    assert result.content_type == "forward"
    assert "Alice" in result.forward_meta
