"""Main message orchestration, access control, routing, and background tasks.

This module replaces the old handlers with a LangGraph-based agent loop.
Module-level singletons are initialized eagerly (session, memory) or
lazily (graph/LLM/embeddings) so imports work without an API key.
"""

import asyncio
import logging

from langchain_core.messages import AIMessage, HumanMessage
from telegram import Update
from telegram.ext import ContextTypes

from .config import (
    ALLOWED_CHAT_IDS,
    DB_PATH,
    GEMINI_API_KEY,
    GEMINI_EMBEDDING_MODEL,
    GEMINI_MODEL,
    MAX_AGENT_STEPS,
    MAX_HISTORY_MESSAGES,
    RECENT_WINDOW_SIZE,
    SUMMARY_MAX_WORDS,
    SUMMARY_THRESHOLD,
)
from .graph import build_context_node, build_graph, should_respond_node
from .memory import BotMemory
from .prompts import SUMMARIZE_PROMPT, SUMMARY_UPDATE_PROMPT
from .session import SessionManager

logger = logging.getLogger(__name__)

# ── Module-level singletons ───────────────────────────────────────────

session_manager = SessionManager(
    max_messages=MAX_HISTORY_MESSAGES,
    recent_window=RECENT_WINDOW_SIZE,
)
bot_memory = BotMemory(db_path=DB_PATH)


# ── Lazy graph / LLM / embeddings ────────────────────────────────────


class _LazyGraph:
    """Defers LLM and embedding initialization until first use.

    This allows the module to be imported without a valid API key
    (useful for testing, where ``compiled_graph`` is patched out).
    """

    def __init__(self):
        self._graph = None
        self._llm = None
        self._embeddings = None

    def _init(self):
        from langchain_google_genai import (
            ChatGoogleGenerativeAI,
            GoogleGenerativeAIEmbeddings,
        )

        self._llm = ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            google_api_key=GEMINI_API_KEY,
            temperature=0.7,
            max_retries=2,
        )
        self._embeddings = GoogleGenerativeAIEmbeddings(
            model=GEMINI_EMBEDDING_MODEL,
            google_api_key=GEMINI_API_KEY,
        )
        self._graph = build_graph(self._llm, bot_memory, self._embeddings.embed_query)

    def invoke(self, state):
        if self._graph is None:
            self._init()
        return self._graph.invoke(
            state, {"recursion_limit": MAX_AGENT_STEPS * 2 + 1}
        )

    def embed(self, text):
        if self._embeddings is None:
            self._init()
        return self._embeddings.embed_query(text)


compiled_graph = _LazyGraph()


# ── Public helpers ────────────────────────────────────────────────────


def embed_text(text: str) -> list[float]:
    """Generate an embedding vector for *text* via the lazy graph embeddings."""
    return compiled_graph.embed(text)


# ── Main message handler ─────────────────────────────────────────────


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process every incoming Telegram text message."""

    # 1. Return early if no message text
    if not update.message or not update.message.text:
        return

    chat_id = update.message.chat_id

    # 2. Return if chat_id not in ALLOWED_CHAT_IDS
    if chat_id not in ALLOWED_CHAT_IDS:
        return

    user = update.message.from_user

    # 3. Return if no user
    if user is None:
        return

    text = update.message.text

    # 4. Build author string
    author = f"{user.first_name or 'Unknown'} [ID: {user.id}]"

    # 5. Store message in session
    session_manager.add_message(chat_id, "user", text, author=author)

    # 6. Check respond conditions
    is_private = update.message.chat.type == "private"
    bot_username = context.bot.username
    is_reply_to_bot = (
        update.message.reply_to_message is not None
        and update.message.reply_to_message.from_user is not None
        and update.message.reply_to_message.from_user.username == bot_username
    )
    is_mention = f"@{bot_username}" in text

    # 7. Call should_respond_node
    result = should_respond_node(
        {},
        is_private=is_private,
        is_reply_to_bot=is_reply_to_bot,
        is_mention=is_mention,
    )
    if not result["should_respond"]:
        return

    # 8. Strip bot mention from question
    question = text.replace(f"@{bot_username}", "").strip() or text

    # 9. Start typing indicator task
    async def _send_typing():
        while True:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(5)

    typing_task = asyncio.create_task(_send_typing())

    try:
        # 10. Get recent messages and summary
        recent_messages = session_manager.get_recent(chat_id)
        summary = session_manager.get_summary(chat_id)

        # 11. Build context messages list
        ctx = build_context_node(
            {"summary": summary},
            recent_messages=recent_messages,
        )
        messages = list(ctx["messages"])

        # 12. Append current question as HumanMessage
        messages.append(HumanMessage(content=f"[{author}]: {question}"))

        # 13. Call compiled_graph.invoke via asyncio.to_thread
        state = {
            "messages": messages,
            "chat_id": chat_id,
            "user_name": author,
            "user_id": user.id,
            "bot_username": bot_username or "",
            "question": question,
            "summary": summary,
            "should_respond": True,
            "response_text": "",
            "used_memory_ids": [],
        }
        result = await asyncio.to_thread(compiled_graph.invoke, state)

        # 14. Extract response: iterate reversed messages for last AIMessage without tool_calls
        response_text = ""
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage) and msg.content:
                if not getattr(msg, "tool_calls", None):
                    response_text = msg.content
                    break

        if not response_text:
            response_text = "I couldn't generate a response. Please try again."

        # 15. Cancel typing, store bot response in session
        typing_task.cancel()
        session_manager.add_message(
            chat_id, "model", response_text, author=bot_username or "bot"
        )

        # 16. Send reply (with 4096-char splitting)
        if len(response_text) <= 4096:
            await update.message.reply_text(response_text)
        else:
            for i in range(0, len(response_text), 4096):
                await update.message.reply_text(response_text[i : i + 4096])

        # 17. Check if summary needed, trigger background _summarize_chat task
        if session_manager.needs_summary(chat_id, threshold=SUMMARY_THRESHOLD):
            task = asyncio.create_task(_summarize_chat(chat_id))
            task.add_done_callback(
                lambda t: logger.error(
                    "Unhandled error in background summarization: %s", t.exception()
                )
                if not t.cancelled() and t.exception() is not None
                else None
            )

    except Exception:
        typing_task.cancel()
        logger.exception("Graph invocation failed")
        await update.message.reply_text(
            "Sorry, something went wrong. Try again."
        )


# ── Background summarization ─────────────────────────────────────────


async def _summarize_chat(chat_id: int) -> None:
    """Generate or update a running conversation summary for *chat_id*."""
    try:
        unsummarized = session_manager.get_unsummarized(chat_id)
        if not unsummarized:
            return

        new_text = "\n".join(
            f"[{m.get('author', 'user')}]: {m['text']}" for m in unsummarized
        )

        existing_summary = session_manager.get_summary(chat_id)

        if existing_summary:
            prompt = SUMMARY_UPDATE_PROMPT.format(
                existing_summary=existing_summary,
                new_messages=new_text,
            )
        else:
            prompt = f"{SUMMARIZE_PROMPT}\n\n{new_text}"

        from langchain_google_genai import ChatGoogleGenerativeAI

        llm = ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            google_api_key=GEMINI_API_KEY,
            temperature=0.3,
        )
        result = await asyncio.to_thread(
            llm.invoke, [HumanMessage(content=prompt)]
        )

        summary = result.content or ""
        # Cap at SUMMARY_MAX_WORDS
        words = summary.split()
        if len(words) > SUMMARY_MAX_WORDS:
            summary = " ".join(words[:SUMMARY_MAX_WORDS])

        session_manager.set_summary(chat_id, summary)
        session_manager.mark_summarized(chat_id, len(unsummarized))
        logger.info("Updated summary for chat %s (%d messages)", chat_id, len(unsummarized))

    except Exception:
        logger.exception("Failed to summarize chat %s", chat_id)
