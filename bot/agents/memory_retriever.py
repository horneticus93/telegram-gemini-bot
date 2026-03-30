"""Memory retriever sub-agent — semantic search over BotMemory."""
from __future__ import annotations
import asyncio
import logging

from .base import BaseSubAgent, SubAgentResult

logger = logging.getLogger(__name__)


class MemoryRetriever(BaseSubAgent):
    name = "memory_retriever"

    def __init__(self, memory, embed_fn, top_k: int = 5):
        self._memory = memory
        self._embed_fn = embed_fn
        self._top_k = top_k

    async def run(self, *, text: str, **kwargs) -> SubAgentResult:
        try:
            embedding = await asyncio.to_thread(self._embed_fn, text)
            results = await asyncio.to_thread(
                self._memory.search_memories,
                query_embedding=embedding,
                limit=self._top_k,
                cooldown_seconds=0,  # retriever always pulls fresh
            )
            if not results:
                return SubAgentResult(
                    agent_name=self.name, content="", metadata={"count": 0, "memories": []}
                )
            lines = [f"- {r['content']}" for r in results]
            return SubAgentResult(
                agent_name=self.name,
                content="\n".join(lines),
                metadata={"count": len(results), "memories": results},
            )
        except Exception as e:
            logger.warning("memory_retriever error: %s", e)
            return SubAgentResult(agent_name=self.name, content="", metadata={"count": 0, "memories": []})
