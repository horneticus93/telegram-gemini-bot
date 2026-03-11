"""Mention detector sub-agent — uses Flash-Lite to determine if bot is addressed."""
from __future__ import annotations
import asyncio
import json
import logging

from .base import BaseSubAgent, SubAgentResult
from .prompts import MENTION_DETECTOR_PROMPT

logger = logging.getLogger(__name__)


class MentionDetector(BaseSubAgent):
    name = "mention_detector"

    def __init__(self, llm, confidence_threshold: float = 0.7):
        self._llm = llm
        self._threshold = confidence_threshold

    async def run(self, *, text: str, bot_aliases: list[str], chat_id: int, **kwargs) -> SubAgentResult:
        aliases_str = ", ".join(bot_aliases) if bot_aliases else "none"
        prompt = MENTION_DETECTOR_PROMPT.format(aliases=aliases_str, text=text)

        from langchain_core.messages import HumanMessage
        response = await asyncio.to_thread(
            self._llm.invoke, [HumanMessage(content=prompt)]
        )

        try:
            data = json.loads(response.content)
            is_addressed = bool(data.get("is_addressed", False))
            confidence = float(data.get("confidence", 0.0))
            new_alias = data.get("new_alias")

            if confidence < self._threshold:
                is_addressed = False

            return SubAgentResult(
                agent_name=self.name,
                content="addressed" if is_addressed else "not_addressed",
                confidence=confidence,
                metadata={
                    "is_addressed": is_addressed,
                    "new_alias": new_alias if new_alias else None,
                },
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning("mention_detector parse error: %s", e)
            return SubAgentResult(
                agent_name=self.name,
                content="not_addressed",
                confidence=0.0,
                metadata={"is_addressed": False, "new_alias": None},
            )
