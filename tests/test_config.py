import os

import pytest
from bot.config import Settings


@pytest.mark.asyncio
async def test_get_returns_default_if_key_missing(db):
    s = Settings(db)
    val = await s.get("nonexistent_key", default="fallback")
    assert val == "fallback"


@pytest.mark.asyncio
async def test_set_and_get(db):
    s = Settings(db)
    await s.set("chat_model", "openai/gpt-4o")
    val = await s.get("chat_model")
    assert val == "openai/gpt-4o"


@pytest.mark.asyncio
async def test_hot_reload(db):
    s = Settings(db)
    await s.set("chat_model", "openai/gpt-4o")
    # simulate external change directly in DB
    await db.execute(
        "UPDATE config SET value = $1 WHERE key = $2",
        '"gemini/gemini-2.5-pro"',
        "chat_model",
    )
    await s.reload()
    val = await s.get("chat_model")
    assert val == "gemini/gemini-2.5-pro"


@pytest.mark.asyncio
async def test_set_sensitive_key_encrypts(db):
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    os.environ["ENCRYPTION_KEY"] = key
    try:
        s = Settings(db)
        await s.set("telegram_bot_token", "secret-token")
        # raw DB value should be encrypted
        raw = await db.fetchval("SELECT value FROM config WHERE key = 'telegram_bot_token'")
        assert raw.startswith('"enc:'), f"Expected encrypted value, got: {raw}"
        # get() should decrypt it
        val = await s.get("telegram_bot_token")
        assert val == "secret-token"
    finally:
        del os.environ["ENCRYPTION_KEY"]
