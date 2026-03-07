"""Main message orchestration, access control, routing, and background tasks.

This module replaces the old handlers with a LangGraph-based agent loop.
Module-level singletons are initialized eagerly (session, memory) or
lazily (graph/LLM/embeddings) so imports work without an API key.
"""

import asyncio
import logging
import time

from langchain_core.messages import AIMessage, HumanMessage
from telegram import Update
from telegram.ext import ContextTypes

from .config import (
    ALLOWED_CHAT_IDS,
    DB_PATH,
    GEMINI_API_KEY,
    GEMINI_EMBEDDING_MODEL,
    GEMINI_FLASH_MODEL,
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
        self._orchestrator = None

    def _init(self):
        from langchain_google_genai import (
            ChatGoogleGenerativeAI,
            GoogleGenerativeAIEmbeddings,
        )
        from bot.config import (
            GEMINI_PRO_MODEL, GEMINI_FLASH_MODEL, GEMINI_FLASH_LITE_MODEL,
            SUBAGENT_TIMEOUT, MEMORY_RETRIEVER_TOP_K, MENTION_DETECTOR_CONFIDENCE,
            MAX_LINKS_PER_MESSAGE,
        )
        from bot.agents.orchestrator import AgentOrchestrator
        from bot.agents.mention_detector import MentionDetector
        from bot.agents.memory_retriever import MemoryRetriever
        from bot.agents.context_analyst import ContextAnalyst
        from bot.agents.image_analyzer import ImageAnalyzer
        from bot.agents.link_extractor import LinkExtractor
        from bot.agents.repost_analyzer import RepostAnalyzer

        self._llm = ChatGoogleGenerativeAI(
            model=GEMINI_PRO_MODEL,
            google_api_key=GEMINI_API_KEY,
            temperature=0.7,
            max_retries=2,
        )
        self._embeddings = GoogleGenerativeAIEmbeddings(
            model=GEMINI_EMBEDDING_MODEL,
            google_api_key=GEMINI_API_KEY,
        )
        self._graph = build_graph(self._llm, bot_memory, self._embeddings.embed_query)

        llm_flash = ChatGoogleGenerativeAI(model=GEMINI_FLASH_MODEL, google_api_key=GEMINI_API_KEY, temperature=0.3)
        llm_lite = ChatGoogleGenerativeAI(model=GEMINI_FLASH_LITE_MODEL, google_api_key=GEMINI_API_KEY, temperature=0.3)

        self._orchestrator = AgentOrchestrator(
            mention_detector=MentionDetector(llm=llm_lite, confidence_threshold=MENTION_DETECTOR_CONFIDENCE),
            memory_retriever=MemoryRetriever(memory=bot_memory, embed_fn=self._embeddings.embed_query, top_k=MEMORY_RETRIEVER_TOP_K),
            context_analyst=ContextAnalyst(llm=llm_lite),
            image_analyzer=ImageAnalyzer(llm=llm_flash),
            link_extractor=LinkExtractor(llm=llm_lite, max_links=MAX_LINKS_PER_MESSAGE),
            repost_analyzer=RepostAnalyzer(llm=llm_lite),
            memory=bot_memory,
        )

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

    async def orchestrate(self, *, text, chat_id, recent_messages, has_photo, has_forward,
                           image_data=None, mime_type="image/jpeg",
                           forwarded_text="", forward_from=None) -> str:
        if self._orchestrator is None:
            self._init()
        return await self._orchestrator.build_pre_context(
            text=text, chat_id=chat_id, recent_messages=recent_messages,
            has_photo=has_photo, has_forward=has_forward,
            image_data=image_data, mime_type=mime_type,
            forwarded_text=forwarded_text, forward_from=forward_from,
        )


compiled_graph = _LazyGraph()


# ── Public helpers ────────────────────────────────────────────────────


def embed_text(text: str) -> list[float]:
    """Generate an embedding vector for *text* via the lazy graph embeddings."""
    return compiled_graph.embed(text)


# ── Main message handler ─────────────────────────────────────────────


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process every incoming Telegram text message."""

    # 1. Return early if no message or no actionable content
    if not update.message:
        return
    text = update.message.text or update.message.caption or ""
    has_content = bool(
        text
        or update.message.photo
        or getattr(update.message, "forward_date", None) is not None
    )
    if not has_content:
        return

    chat_id = update.message.chat_id

    # 2. Return if chat_id not in ALLOWED_CHAT_IDS
    if chat_id not in ALLOWED_CHAT_IDS:
        return

    user = update.message.from_user

    # 3. Return if no user
    if user is None:
        return

    # 4. Build author string
    author = f"{user.first_name or 'Unknown'} [ID: {user.id}]"

    logger.info(
        "Message received | chat_id=%s author=%r type=%s text=%r",
        chat_id, author, update.message.chat.type, text[:120],
    )

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

    # Check if any stored bot alias appears in the text (name-based addressing)
    bot_aliases = await asyncio.to_thread(bot_memory.get_bot_aliases, chat_id)
    text_lower = text.lower()
    is_named = any(alias.lower() in text_lower for alias in bot_aliases)
    if is_named:
        logger.info("Bot addressed by alias | chat_id=%s aliases=%s", chat_id, bot_aliases)

    # 7. Call should_respond_node
    result = should_respond_node(
        {},
        is_private=is_private,
        is_reply_to_bot=is_reply_to_bot,
        is_mention=is_mention or is_named,
    )
    if not result["should_respond"]:
        logger.info(
            "Not responding | chat_id=%s private=%s reply=%s mention=%s named=%s",
            chat_id, is_private, is_reply_to_bot, is_mention, is_named,
        )
        return

    logger.info(
        "Responding | chat_id=%s private=%s reply=%s mention=%s named=%s",
        chat_id, is_private, is_reply_to_bot, is_mention, is_named,
    )

    # 8. Strip bot mention from question
    question = text.replace(f"@{bot_username}", "").strip() or text

    # 9. Start typing indicator task
    async def _send_typing():
        while True:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(5)

    typing_task = asyncio.create_task(_send_typing())

    t_start = time.monotonic()

    try:
        # 10. Get recent messages and summary
        recent_messages = session_manager.get_recent(chat_id)
        summary = session_manager.get_summary(chat_id)
        logger.info(
            "Session context | chat_id=%s recent=%d has_summary=%s",
            chat_id, len(recent_messages), bool(summary),
        )

        # 10b. Detect content types
        has_photo = bool(update.message.photo)
        has_forward = getattr(update.message, "forward_date", None) is not None
        has_url = bool(__import__("re").search(r"https?://", text))
        logger.info(
            "Content detection | chat_id=%s has_photo=%s has_forward=%s has_url=%s",
            chat_id, has_photo, has_forward, has_url,
        )

        # Download photo bytes if present (current message or replied-to message)
        image_data: bytes | None = None
        mime_type = "image/jpeg"
        reply_msg = update.message.reply_to_message
        photo_source = (
            update.message.photo
            or (reply_msg.photo if reply_msg and reply_msg.photo else None)
        )
        if photo_source:
            has_photo = True
            tg_file = await context.bot.get_file(photo_source[-1].file_id)
            image_bytes = await tg_file.download_as_bytearray()
            image_data = bytes(image_bytes)
            logger.info("Photo downloaded | chat_id=%s size=%d bytes", chat_id, len(image_data))

        forwarded_text = ""
        forward_from = None
        if has_forward and update.message.forward_origin:
            forwarded_text = text
            origin = update.message.forward_origin
            if hasattr(origin, "sender_user") and origin.sender_user:
                forward_from = origin.sender_user.first_name
            logger.info("Forward detected | chat_id=%s from=%r", chat_id, forward_from)

        # Run sub-agent orchestrator
        logger.info("Orchestrator starting | chat_id=%s", chat_id)
        t_orch = time.monotonic()
        pre_context = await compiled_graph.orchestrate(
            text=question,
            chat_id=chat_id,
            recent_messages=recent_messages,
            has_photo=has_photo,
            has_forward=has_forward,
            image_data=image_data,
            mime_type=mime_type,
            forwarded_text=forwarded_text,
            forward_from=forward_from,
        )
        logger.info(
            "Orchestrator done | chat_id=%s elapsed=%.2fs pre_context_len=%d",
            chat_id, time.monotonic() - t_orch, len(pre_context),
        )

        # 11. Build context messages list
        ctx = build_context_node(
            {"summary": summary},
            recent_messages=recent_messages,
        )
        messages = list(ctx["messages"])

        # 12. Append current question as HumanMessage
        messages.append(HumanMessage(content=f"[{author}]: {question}"))

        # 13. Call compiled_graph.invoke via asyncio.to_thread
        logger.info("Main agent invoked | chat_id=%s messages=%d", chat_id, len(messages))
        t_agent = time.monotonic()
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
            "pre_context": pre_context,
        }
        result = await asyncio.to_thread(compiled_graph.invoke, state)
        logger.info(
            "Main agent done | chat_id=%s elapsed=%.2fs",
            chat_id, time.monotonic() - t_agent,
        )

        # 14. Extract response: iterate reversed messages for last AIMessage without tool_calls
        response_text = ""
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage) and msg.content:
                if not getattr(msg, "tool_calls", None):
                    content = msg.content
                    if isinstance(content, list):
                        response_text = "".join(
                            block.get("text", "")
                            for block in content
                            if isinstance(block, dict)
                        )
                    else:
                        response_text = content
                    break

        if not response_text:
            response_text = "I couldn't generate a response. Please try again."

        # 15. Cancel typing, store bot response in session
        typing_task.cancel()
        session_manager.add_message(
            chat_id, "model", response_text, author=bot_username or "bot"
        )

        # 16. Send reply (with 4096-char splitting)
        parts = (len(response_text) + 4095) // 4096
        logger.info(
            "Sending reply | chat_id=%s length=%d parts=%d total_elapsed=%.2fs",
            chat_id, len(response_text), parts, time.monotonic() - t_start,
        )
        if len(response_text) <= 4096:
            await update.message.reply_text(response_text)
        else:
            for i in range(0, len(response_text), 4096):
                await update.message.reply_text(response_text[i : i + 4096])

        # 17. Check if summary needed, trigger background _summarize_chat task
        if session_manager.needs_summary(chat_id, threshold=SUMMARY_THRESHOLD):
            logger.info("Triggering background summarization | chat_id=%s", chat_id)
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
        logger.exception("Graph invocation failed | chat_id=%s elapsed=%.2fs", chat_id, time.monotonic() - t_start)
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
        logger.info("Summarization started | chat_id=%s messages=%d", chat_id, len(unsummarized))

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
            model=GEMINI_FLASH_MODEL,
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
