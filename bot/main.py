import logging
import os

from dotenv import load_dotenv

load_dotenv()

from telegram.ext import Application, MessageHandler, filters

from .config import TELEGRAM_BOT_TOKEN, GEMINI_API_KEY
from .handlers import handle_message, bot_memory

_log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=_log_level,
)
logger = logging.getLogger(__name__)


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY environment variable is not set")

    bot_memory.init_db()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(
        MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.FORWARDED) & ~filters.COMMAND,
            handle_message,
        )
    )

    logger.info("Bot v2.0.0 starting, polling for updates...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
