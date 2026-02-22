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

    def extract_facts(
        self,
        existing_facts: list[str],
        recent_history: str,
        user_name: str,
    ) -> list[dict]:
        return self._get().extract_facts(
            existing_facts=existing_facts,
            recent_history=recent_history,
            user_name=user_name,
        )

    def decide_fact_action(
        self,
        candidate_fact: str,
        scope: str,
        similar_facts: list[dict],
        user_name: str,
    ) -> dict:
        return self._get().decide_fact_action(
            candidate_fact=candidate_fact,
            scope=scope,
            similar_facts=similar_facts,
            user_name=user_name,
        )

gemini_client: _LazyGeminiClient = _LazyGeminiClient()


async def _update_user_profile(
    user_id: int, chat_id: int, user_name: str
) -> None:
    try:
        existing_facts = user_memory.get_user_facts(user_id=user_id, limit=40)
        recent_history = session_manager.format_history(chat_id)
        extracted_facts = gemini_client.extract_facts(
            existing_facts=existing_facts,
            recent_history=recent_history,
            user_name=f"{user_name} [ID: {user_id}]",
        )
        if not extracted_facts:
            return

        user_facts = []
        chat_facts = []
        for item in extracted_facts:
            fact_text = str(item.get("fact", "")).strip()
            if not fact_text:
                continue
            scoped_fact = dict(item)
            scoped_fact["embedding"] = gemini_client.embed_text(fact_text)
            if item.get("scope") == "chat":
                similar_facts = user_memory.find_similar_facts(
                    scope="chat",
                    query_embedding=scoped_fact["embedding"],
                    chat_id=chat_id,
                    limit=3,
                )
                if similar_facts:
                    scoped_fact.update(
                        gemini_client.decide_fact_action(
                            candidate_fact=fact_text,
                            scope="chat",
                            similar_facts=similar_facts,
                            user_name=user_name,
                        )
                    )
                chat_facts.append(scoped_fact)
            else:
                similar_facts = user_memory.find_similar_facts(
                    scope="user",
                    query_embedding=scoped_fact["embedding"],
                    user_id=user_id,
                    limit=3,
                )
                if similar_facts:
                    scoped_fact.update(
                        gemini_client.decide_fact_action(
                            candidate_fact=fact_text,
                            scope="user",
                            similar_facts=similar_facts,
                            user_name=user_name,
                        )
                    )
                user_facts.append(scoped_fact)

        if user_facts:
            user_memory.upsert_user_facts(user_id=user_id, chat_id=chat_id, facts=user_facts)
        if chat_facts:
            user_memory.upsert_chat_facts(chat_id=chat_id, facts=chat_facts)
        logger.info("Updated fact memory for user %s (%s)", user_id, user_name)
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
    user_facts = user_memory.get_user_facts(user_id=user.id, limit=8)
    if user_facts:
        user_profile = "\n".join(f"- {fact}" for fact in user_facts)
    else:
        user_profile = user_memory.get_profile(user.id)
    chat_members = user_memory.get_chat_members(chat_id)

    async def send_typing():
        while True:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(5)

    typing_task = asyncio.create_task(send_typing())

    try:
        # Retrieve relevant memory facts for RAG only when similarity is sufficient.
        query_embedding = await asyncio.to_thread(gemini_client.embed_text, question)
        fact_results = user_memory.search_facts_by_embedding(
            query_embedding=query_embedding,
            chat_id=chat_id,
            asking_user_id=user.id,
            limit=3,
        )
        retrieved_profiles = (
            [_format_fact_for_prompt(fact) for fact in fact_results]
            if fact_results
            else None
        )

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
        if fact_results:
            user_memory.mark_facts_used([fact["fact_id"] for fact in fact_results])

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


def _format_fact_for_prompt(fact: dict) -> str:
    scope = fact.get("scope")
    if scope == "chat":
        return f"[chat fact] {fact['fact_text']}"
    owner = fact.get("owner_name", "Unknown")
    owner_id = fact.get("user_id")
    if owner_id is not None:
        return f"[user fact] {owner} [ID: {owner_id}]: {fact['fact_text']}"
    return f"[user fact] {owner}: {fact['fact_text']}"
