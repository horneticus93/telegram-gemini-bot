import json
import os

from cryptography.fernet import Fernet


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")

ALLOWED_CHAT_IDS: set[int] = {
    int(cid.strip())
    for cid in os.getenv("ALLOWED_CHAT_IDS", "").split(",")
    if cid.strip()
}

DB_PATH = os.getenv("DB_PATH", "/app/data/memory.db")
MAX_HISTORY_MESSAGES = int(os.getenv("MAX_HISTORY_MESSAGES", "50"))

SUMMARY_THRESHOLD = int(os.getenv("SUMMARY_THRESHOLD", "30"))
SUMMARY_MAX_WORDS = int(os.getenv("SUMMARY_MAX_WORDS", "500"))
RECENT_WINDOW_SIZE = int(os.getenv("RECENT_WINDOW_SIZE", "15"))
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", "6"))

# Multi-agent models
GEMINI_PRO_MODEL = os.getenv("GEMINI_PRO_MODEL", "gemini-2.5-pro")
GEMINI_FLASH_MODEL = os.getenv("GEMINI_FLASH_MODEL", "gemini-2.0-flash")
GEMINI_FLASH_LITE_MODEL = os.getenv("GEMINI_FLASH_LITE_MODEL", "gemini-2.0-flash-lite")

# Agent system tuning
ORCHESTRATOR_TIMEOUT = int(os.getenv("ORCHESTRATOR_TIMEOUT", "15"))
SUBAGENT_TIMEOUT = int(os.getenv("SUBAGENT_TIMEOUT", "8"))
MAX_LINKS_PER_MESSAGE = int(os.getenv("MAX_LINKS_PER_MESSAGE", "3"))
MENTION_DETECTOR_CONFIDENCE = float(os.getenv("MENTION_DETECTOR_CONFIDENCE", "0.7"))
MEMORY_RETRIEVER_TOP_K = int(os.getenv("MEMORY_RETRIEVER_TOP_K", "5"))
RELEVANCE_JUDGE_THRESHOLD = float(os.getenv("RELEVANCE_JUDGE_THRESHOLD", "0.6"))


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
        self._fernet: Fernet | None = None
        key = os.environ.get("ENCRYPTION_KEY")
        if key:
            self._fernet = Fernet(key.encode())

    async def _load_all(self) -> dict:
        rows = await self._pool.fetch("SELECT key, value FROM config")
        return {r["key"]: json.loads(r["value"]) for r in rows}

    async def reload(self) -> None:
        self._cache = await self._load_all()

    async def get(self, key: str, default=None):
        if not self._cache:
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
            VALUES ($1, $2::jsonb, now())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
            """,
            key,
            json_val,
        )
        self._cache[key] = json.loads(json_val)

    def _encrypt(self, plaintext: str) -> str:
        assert self._fernet, "ENCRYPTION_KEY not set"
        return self._fernet.encrypt(plaintext.encode()).decode()

    def _decrypt(self, token: str) -> str:
        assert self._fernet, "ENCRYPTION_KEY not set"
        return self._fernet.decrypt(token.encode()).decode()
