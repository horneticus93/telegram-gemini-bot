import os
import logging
from dotenv import load_dotenv
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
from .handlers import handle_message
from .memory_handlers import (
    handle_memory_callback,
    handle_memory_command,
    handle_memory_edit_reply,
)
from .scheduler import register_jobs

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def _message_dispatcher(update, context):
    """Dispatch text messages: try edit-reply first, then normal handler."""
    consumed = await handle_memory_edit_reply(update, context)
    if not consumed:
        await handle_message(update, context)


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")

    if not os.getenv("GEMINI_API_KEY"):
        raise ValueError("GEMINI_API_KEY environment variable is not set")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("memory", handle_memory_command))
    app.add_handler(CallbackQueryHandler(handle_memory_callback, pattern=r"^mem:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _message_dispatcher))

    register_jobs(app)

    logger.info("Bot starting, polling for updates...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

