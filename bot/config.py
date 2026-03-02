import os


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
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
