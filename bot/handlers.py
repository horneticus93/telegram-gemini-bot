import asyncio
import logging
from telegram import Update, Bot
from telegram.ext import ContextTypes
from bot.processor import MessageProcessor
from bot.context import ContextBuilder
from bot.llm import LLMService
from bot.session import SessionManager

logger = logging.getLogger(__name__)
TELEGRAM_MAX_LEN = 4096


def should_respond(update, bot_username: str, allowed_chat_ids: set[int]) -> bool:
    msg = update.message
    if not msg:
        return False
    if msg.chat_id not in allowed_chat_ids:
        return False
    if msg.chat.type == "private":
        return True
    # Group: only respond when mentioned or reply-to-bot
    if msg.reply_to_message and msg.reply_to_message.from_user and msg.reply_to_message.from_user.is_bot:
        return True
    text = msg.text or msg.caption or ""
    if f"@{bot_username}" in text:
        return True
    if msg.entities:
        for ent in msg.entities:
            if ent.type == "mention":
                return True
    return False


def split_message(text: str, max_len: int = TELEGRAM_MAX_LEN) -> list[str]:
    if len(text) <= max_len:
        return [text]
    parts = []
    while text:
        parts.append(text[:max_len])
        text = text[max_len:]
    return parts


class MessageHandler:
    def __init__(
        self,
        settings,
        session: SessionManager,
        processor: MessageProcessor,
        context_builder: ContextBuilder,
        llm: LLMService,
        pool,
    ) -> None:
        self._settings = settings
        self._session = session
        self._processor = processor
        self._ctx_builder = context_builder
        self._llm = llm
        self._pool = pool

    async def handle(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = update.message
        if not msg:
            return

        bot_username = context.bot.username
        allowed = set(await self._settings.get("allowed_chat_ids", default=[]))

        if msg.chat_id not in allowed:
            return

        # Always store message in session
        text = msg.text or msg.caption or ""
        author = getattr(msg.from_user, "full_name", "") or ""
        self._session.add_message(chat_id=msg.chat_id, role="user", text=text, author=author)

        if not should_respond(update, bot_username=bot_username, allowed_chat_ids=allowed):
            return

        # Process content
        processed = await self._processor.process(msg, bot=context.bot)

        # Build context
        messages = await self._ctx_builder.build(chat_id=msg.chat_id, processed=processed)

        # LLM call
        try:
            result = await self._llm.complete(messages, has_image=processed.image_bytes is not None)
        except Exception as e:
            logger.exception("LLM error: %s", e)
            await msg.reply_text("Sorry, something went wrong.")
            return

        # Store assistant response in session
        self._session.add_message(chat_id=msg.chat_id, role="assistant", text=result.text, author="bot")

        # Send reply (split if needed)
        for chunk in split_message(result.text):
            await msg.reply_text(chunk)

        # Persist log + trigger summarization in background
        asyncio.create_task(self._post_response(msg, processed, result))

    async def _post_response(self, msg, processed, result) -> None:
        try:
            await self._pool.execute(
                """
                INSERT INTO message_logs (chat_id, user_id, username, role, content, content_type, tokens_used, model_used, created_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,now())
                """,
                msg.chat_id,
                getattr(msg.from_user, "id", None),
                getattr(msg.from_user, "username", None),
                "user",
                processed.text or "",
                processed.content_type,
                result.tokens_used,
                result.model_used,
            )
            await self._session.maybe_summarize(msg.chat_id)
        except Exception as e:
            logger.warning("post_response error: %s", e)
