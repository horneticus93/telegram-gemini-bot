import json
import os
from cryptography.fernet import Fernet


_SENSITIVE_KEYS = {
    "telegram_bot_token", "gemini_api_key", "openai_api_key",
    "anthropic_api_key", "openrouter_api_key", "tavily_api_key",
}

_DEFAULTS = {
    "chat_model": "gemini/gemini-2.5-pro",
    "vision_model": "gemini/gemini-2.0-flash",
    "embedding_model": "gemini/gemini-embedding-001",
    "summarization_model": "gemini/gemini-2.0-flash",
    "max_history_messages": 50,
    "summary_threshold": 30,
    "summary_max_words": 500,
    "memory_search_limit": 5,
    "memory_similarity_threshold": 0.75,
    "max_links_per_message": 3,
    "max_response_length": 4096,
    "respond_in_groups_only_when_mentioned": True,
    "system_prompt": "You are a helpful assistant.",
    "bot_language": "uk",
    "allowed_chat_ids": [],
    "admin_telegram_ids": [],
}


class Settings:
    def __init__(self, pool) -> None:
        self._pool = pool
        self._cache: dict = {}
        self._loaded: bool = False
        self._fernet: Fernet | None = None
        key = os.environ.get("ENCRYPTION_KEY")
        if key:
            self._fernet = Fernet(key.encode())

    async def _load_all(self) -> dict:
        rows = await self._pool.fetch("SELECT key, value FROM config")
        return {r["key"]: json.loads(r["value"]) for r in rows}

    async def reload(self) -> None:
        self._cache = await self._load_all()
        self._loaded = True

    async def get(self, key: str, default=None):
        if not self._loaded:
            await self.reload()
        val = self._cache.get(key, _DEFAULTS.get(key, default))
        if key in _SENSITIVE_KEYS and isinstance(val, str) and val.startswith("enc:"):
            val = self._decrypt(val[4:])
        return val

    async def set(self, key: str, value) -> None:
        if key in _SENSITIVE_KEYS and isinstance(value, str) and self._fernet:
            value = "enc:" + self._encrypt(value)
        json_val = json.dumps(value)
        await self._pool.execute(
            """
            INSERT INTO config (key, value, updated_at)
            VALUES ($1, $2, now())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
            """,
            key,
            json_val,
        )
        self._cache[key] = json.loads(json_val)

    def _encrypt(self, plaintext: str) -> str:
        if not self._fernet:
            raise RuntimeError("ENCRYPTION_KEY not set")
        return self._fernet.encrypt(plaintext.encode()).decode()

    def _decrypt(self, token: str) -> str:
        if not self._fernet:
            raise RuntimeError("ENCRYPTION_KEY not set")
        return self._fernet.decrypt(token.encode()).decode()
