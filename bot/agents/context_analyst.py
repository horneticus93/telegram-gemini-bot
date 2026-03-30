"""Context analyst sub-agent — analyzes recent messages for tone and topics."""
from __future__ import annotations
import asyncio
import json
import logging

from .base import BaseSubAgent, SubAgentResult
from .prompts import CONTEXT_ANALYST_PROMPT

logger = logging.getLogger(__name__)


class ContextAnalyst(BaseSubAgent):
    name = "context_analyst"

    def __init__(self, llm):
        self._llm = llm

    async def run(self, *, recent_messages: list[dict], **kwargs) -> SubAgentResult:
        if not recent_messages:
            return SubAgentResult(agent_name=self.name, content="", metadata={})

        lines = [f"[{m.get('author', 'user')}]: {m['text']}" for m in recent_messages[-10:]]
        messages_text = "\n".join(lines)
        prompt = CONTEXT_ANALYST_PROMPT.format(n=len(lines), messages=messages_text)

        from langchain_core.messages import HumanMessage
        try:
            response = await asyncio.to_thread(
                self._llm.invoke, [HumanMessage(content=prompt)]
            )
            content = response.content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            data = json.loads(content)
            summary = data.get("summary", "")
            return SubAgentResult(
                agent_name=self.name,
                content=summary,
                metadata=data,
            )
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("context_analyst error: %s", e)
            return SubAgentResult(agent_name=self.name, content="", metadata={})
