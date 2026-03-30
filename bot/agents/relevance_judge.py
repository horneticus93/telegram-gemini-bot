"""Relevance judge — filters sub-agent results to only useful ones."""
from __future__ import annotations
import asyncio
import json
import logging

from .base import BaseSubAgent, SubAgentResult
from .prompts import RELEVANCE_JUDGE_PROMPT

logger = logging.getLogger(__name__)


class RelevanceJudge(BaseSubAgent):
    name = "relevance_judge"

    def __init__(self, llm, threshold: float = 0.6):
        self._llm = llm
        self._threshold = threshold

    async def run(
        self,
        *,
        text: str,
        sub_agent_results: list[SubAgentResult],
        **kwargs,
    ) -> list[SubAgentResult]:
        if not sub_agent_results:
            return []

        # Pre-filter by confidence threshold before calling LLM
        confident_results = [r for r in sub_agent_results if r.confidence >= self._threshold]
        if not confident_results:
            return []

        results_text = "\n".join(
            f"[{r.agent_name}]: {r.content[:200]}"
            for r in confident_results
            if r.content
        )
        prompt = RELEVANCE_JUDGE_PROMPT.format(text=text, results=results_text)

        from langchain_core.messages import HumanMessage
        try:
            response = await asyncio.to_thread(self._llm.invoke, [HumanMessage(content=prompt)])
            relevant_names: list[str] = json.loads(response.content)
            return [r for r in confident_results if r.agent_name in relevant_names]
        except Exception as e:
            logger.warning("relevance_judge error: %s, returning all", e)
            return confident_results
