import asyncio
import logging
import os
import sys

import uvicorn
from telegram.ext import Application, MessageHandler as TGMessageHandler, filters

from db.pool import get_pool, close_pool
from bot.config import Settings
from bot.session import SessionManager
from bot.processor import MessageProcessor
from bot.context import ContextBuilder
from bot.llm import LLMService
from memory.graph import GraphMemory
from memory.embeddings import EmbeddingService
from bot.handlers import MessageHandler
from bot.tools import execute_tool

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)


async def build_app():
    pool = await get_pool()
    settings = Settings(pool)
    await settings.reload()

    # Seed initial settings from ENV if not yet in DB
    for key, env_var in [
        ("telegram_bot_token", "TELEGRAM_BOT_TOKEN"),
        ("gemini_api_key", "GEMINI_API_KEY"),
        ("allowed_chat_ids", "ALLOWED_CHAT_IDS"),
        ("admin_telegram_ids", "ADMIN_TELEGRAM_IDS"),
        ("chat_model", "CHAT_MODEL"),
        ("vision_model", "VISION_MODEL"),
        ("embedding_model", "EMBEDDING_MODEL"),
        ("summarization_model", "SUMMARIZATION_MODEL"),
    ]:
        if await settings.get(key) is None and os.environ.get(env_var):
            raw = os.environ[env_var]
            if key in ("allowed_chat_ids", "admin_telegram_ids"):
                value = [int(x.strip()) for x in raw.split(",") if x.strip()]
            else:
                value = raw
            await settings.set(key, value)

    graph = GraphMemory(pool)
    embeddings = EmbeddingService(settings, pool)

    async def memory_search(query: str, limit: int):
        ids = await embeddings.search_text(query, limit=limit)
        return await graph.search_by_ids(ids)

    session = SessionManager(settings)
    processor = MessageProcessor(settings)
    ctx_builder = ContextBuilder(session=session, memory_search=memory_search, settings=settings)
    llm = LLMService(settings=settings, graph=graph, embeddings=embeddings)
    handler = MessageHandler(
        settings=settings, session=session, processor=processor,
        context_builder=ctx_builder, llm=llm, pool=pool,
    )

    token = await settings.get("telegram_bot_token")
    tg_app = Application.builder().token(token).build()
    tg_app.add_handler(TGMessageHandler(filters.ALL, handler.handle))

    return tg_app, pool


async def main():
    tg_app, pool = await build_app()

    # Placeholder FastAPI app (web panel added in Plan B)
    from fastapi import FastAPI
    web_app = FastAPI()

    @web_app.get("/health")
    async def health():
        return {"status": "ok"}

    config = uvicorn.Config(web_app, host="0.0.0.0", port=8000, loop="none")
    server = uvicorn.Server(config)

    try:
        await asyncio.gather(
            tg_app.run_polling(close_loop=False),
            server.serve(),
        )
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
