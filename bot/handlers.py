import os
import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes
from .session import SessionManager
from .gemini import GeminiClient
from .memory import UserMemory

logger = logging.getLogger(__name__)

ALLOWED_CHAT_IDS: set[int] = {
    int(cid.strip())
    for cid in os.getenv("ALLOWED_CHAT_IDS", "").split(",")
    if cid.strip()
}

MEMORY_UPDATE_INTERVAL = int(os.getenv("MEMORY_UPDATE_INTERVAL", "10"))

session_manager = SessionManager(
    max_messages=int(os.getenv("MAX_HISTORY_MESSAGES", "100"))
)
user_memory = UserMemory(db_path=os.getenv("DB_PATH", "/app/data/memory.db"))


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

    def ask(
        self,
        history: list[dict],
        question: str,
        user_profile: str = "",
        chat_members: list[str] | None = None,
        retrieved_profiles: list[str] | None = None,
    ) -> tuple[str, bool]:
        return self._get().ask(
            history=history,
            question=question,
            user_profile=user_profile,
            chat_members=chat_members,
            retrieved_profiles=retrieved_profiles,
        )

    def extract_profile(
        self, existing_profile: str, recent_history: str, user_name: str
    ) -> str:
        return self._get().extract_profile(
            existing_profile=existing_profile,
            recent_history=recent_history,
            user_name=user_name,
        )

    def embed_text(self, text: str) -> list[float]:
        return self._get().embed_text(text)

gemini_client: _LazyGeminiClient = _LazyGeminiClient()


async def _update_user_profile(
    user_id: int, chat_id: int, user_name: str
) -> None:
    try:
        existing_profile = user_memory.get_profile(user_id)
        recent_history = session_manager.format_history(chat_id)
        new_profile = gemini_client.extract_profile(
            existing_profile=existing_profile,
            recent_history=recent_history,
            user_name=f"{user_name} [ID: {user_id}]",
        )
        new_embedding = gemini_client.embed_text(new_profile) if new_profile else None
        user_memory.update_profile(user_id, new_profile, embedding=new_embedding)
        logger.info("Updated memory profile for user %s (%s)", user_id, user_name)
    except Exception:
        logger.exception("Failed to update profile for user %s", user_id)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    chat_id = update.message.chat_id
    if chat_id not in ALLOWED_CHAT_IDS:
        return

    user = update.message.from_user
    if user is None:
        return
    author = f"{user.first_name or 'Unknown'} [ID: {user.id}]"
    text = update.message.text
    session_manager.add_message(chat_id, "user", text, author=author)

    msg_count = user_memory.increment_message_count(
        user_id=user.id,
        chat_id=chat_id,
        username=user.username or "",
        first_name=author,
    )
    if msg_count % MEMORY_UPDATE_INTERVAL == 0:
        task = asyncio.create_task(_update_user_profile(user.id, chat_id, author))
        task.add_done_callback(
            lambda t: logger.error("Unhandled error in background profile update: %s", t.exception())
            if not t.cancelled() and t.exception() is not None
            else None
        )
    is_private = update.message.chat.type == "private"
    bot_username = context.bot.username
    is_reply_to_bot = (
        update.message.reply_to_message is not None
        and update.message.reply_to_message.from_user is not None
        and update.message.reply_to_message.from_user.username == bot_username
    )
    if not is_private and not is_reply_to_bot and f"@{bot_username}" not in text:
        return

    question = text.replace(f"@{bot_username}", "").strip() or text

    history = session_manager.get_history(chat_id)
    user_profile = user_memory.get_profile(user.id)
    chat_members = user_memory.get_chat_members(chat_id)

    async def send_typing():
        while True:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(5)

    typing_task = asyncio.create_task(send_typing())

    try:
        # Perform Vector Search for RAG
        query_embedding = await asyncio.to_thread(gemini_client.embed_text, question)
        search_results = user_memory.search_profiles_by_embedding(query_embedding, limit=3)
        retrieved_profiles = [f"{name} [ID: {uid}]: {prof}" for uid, name, prof in search_results] if search_results else None

        response, save_to_profile = await asyncio.to_thread(
            gemini_client.ask,
            history=history,
            question=question,
            user_profile=user_profile,
            chat_members=[f"{name} [ID: {uid}]" for uid, name in chat_members],
            retrieved_profiles=retrieved_profiles,
        )
        typing_task.cancel()
        session_manager.add_message(chat_id, "model", response, author=bot_username or "bot")

        if save_to_profile:
            logger.info("Model flagged save_to_profile for user %s", user.id)
            await _update_user_profile(user.id, chat_id, author)

        if len(response) <= 4096:
            await update.message.reply_text(response)
        else:
            for i in range(0, len(response), 4096):
                await update.message.reply_text(response[i : i + 4096])
    except Exception:
        typing_task.cancel()
        logger.exception("Gemini API call failed")
        await update.message.reply_text(
            "Sorry, something went wrong. Try again."
        )
