"""Memory watcher sub-agent — identifies and saves important facts."""
from __future__ import annotations
import asyncio
import json
import logging

from .base import BaseSubAgent, SubAgentResult
from .prompts import MEMORY_WATCHER_PROMPT

logger = logging.getLogger(__name__)


class MemoryWatcher(BaseSubAgent):
    name = "memory_watcher"

    def __init__(self, llm, memory, embed_fn):
        self._llm = llm
        self._memory = memory
        self._embed_fn = embed_fn

    async def run(self, *, messages: list[dict], **kwargs) -> SubAgentResult:
        if not messages:
            return SubAgentResult(agent_name=self.name, content="", metadata={"saved": 0})

        lines = [f"[{m.get('author', 'user')}]: {m['text']}" for m in messages]
        prompt = MEMORY_WATCHER_PROMPT.format(messages="\n".join(lines))

        from langchain_core.messages import HumanMessage
        try:
            response = await asyncio.to_thread(self._llm.invoke, [HumanMessage(content=prompt)])
            facts = json.loads(response.content)
        except Exception as e:
            logger.warning("memory_watcher parse error: %s", e)
            return SubAgentResult(agent_name=self.name, content="", metadata={"saved": 0})

        saved = 0
        for item in facts:
            fact = item.get("fact", "")
            importance = float(item.get("importance", 0.5))
            if not fact:
                continue
            try:
                embedding = await asyncio.to_thread(self._embed_fn, fact)
                await asyncio.to_thread(
                    self._memory.save_or_update,
                    content=fact,
                    embedding=embedding,
                    importance=importance,
                    source="memory_watcher",
                )
                saved += 1
            except Exception as e:
                logger.warning("memory_watcher save error: %s", e)

        return SubAgentResult(
            agent_name=self.name,
            content=f"Saved {saved} facts",
            metadata={"saved": saved},
        )
