import os
import logging
from telegram import Update
from telegram.ext import ContextTypes
from .session import SessionManager
from .gemini import GeminiClient

logger = logging.getLogger(__name__)

ALLOWED_CHAT_IDS: set[int] = {
    int(cid.strip())
    for cid in os.getenv("ALLOWED_CHAT_IDS", "").split(",")
    if cid.strip()
}

session_manager = SessionManager(
    max_messages=int(os.getenv("MAX_HISTORY_MESSAGES", "100"))
)


class _LazyGeminiClient:
    """Wraps GeminiClient with lazy initialisation so the module can be
    imported without a valid GEMINI_API_KEY (e.g. during tests).  Tests that
    patch ``bot.handlers.gemini_client`` replace this object entirely, so the
    lazy logic is never exercised in that path."""

    def __init__(self) -> None:
        self._client: GeminiClient | None = None

    def _get(self) -> GeminiClient:
        if self._client is None:
            self._client = GeminiClient(api_key=os.getenv("GEMINI_API_KEY", ""))
        return self._client

    def ask(self, history: str, question: str) -> str:
        return self._get().ask(history=history, question=question)


gemini_client: _LazyGeminiClient = _LazyGeminiClient()


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    chat_id = update.message.chat_id
    if chat_id not in ALLOWED_CHAT_IDS:
        return

    user = update.message.from_user
    if user is None:
        return
    author = user.first_name or user.username or "Unknown"
    text = update.message.text

    session_manager.add_message(chat_id, author, text)

    is_private = update.message.chat.type == "private"
    bot_username = context.bot.username
    if not is_private and f"@{bot_username}" not in text:
        return

    question = text.replace(f"@{bot_username}", "").strip() or text
    history = session_manager.format_history(chat_id)

    try:
        response = gemini_client.ask(history=history, question=question)
        if len(response) <= 4096:
            await update.message.reply_text(response)
        else:
            for i in range(0, len(response), 4096):
                await update.message.reply_text(response[i : i + 4096])
    except Exception:
        logger.exception("Gemini API call failed")
        await update.message.reply_text(
            "Sorry, something went wrong. Try again."
        )
