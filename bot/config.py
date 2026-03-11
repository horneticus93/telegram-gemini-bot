import os


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
