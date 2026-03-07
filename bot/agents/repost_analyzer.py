"""Repost analyzer sub-agent — summarizes forwarded messages."""
from __future__ import annotations
import asyncio
import json
import logging

from .base import BaseSubAgent, SubAgentResult
from .prompts import REPOST_ANALYZER_PROMPT

logger = logging.getLogger(__name__)


class RepostAnalyzer(BaseSubAgent):
    name = "repost_analyzer"

    def __init__(self, llm):
        self._llm = llm

    async def run(self, *, forwarded_text: str, forward_from: str | None = None, **kwargs) -> SubAgentResult:
        if not forwarded_text:
            return SubAgentResult(agent_name=self.name, content="", metadata={})

        from langchain_core.messages import HumanMessage
        prompt = REPOST_ANALYZER_PROMPT.format(content=forwarded_text)
        try:
            response = await asyncio.to_thread(self._llm.invoke, [HumanMessage(content=prompt)])
            data = json.loads(response.content)
            source = data.get("source") or forward_from
            summary = data.get("summary", "")
            return SubAgentResult(
                agent_name=self.name,
                content=summary,
                metadata={"source": source, "summary": summary},
            )
        except Exception as e:
            logger.warning("repost_analyzer error: %s", e)
            return SubAgentResult(agent_name=self.name, content="", metadata={})
