"""Image analyzer sub-agent — uses Flash (vision) to describe images."""
from __future__ import annotations
import asyncio
import base64
import logging

from .base import BaseSubAgent, SubAgentResult
from .prompts import IMAGE_ANALYZER_PROMPT

logger = logging.getLogger(__name__)


class ImageAnalyzer(BaseSubAgent):
    name = "image_analyzer"

    def __init__(self, llm):
        self._llm = llm

    async def run(self, *, image_data: bytes, mime_type: str = "image/jpeg", **kwargs) -> SubAgentResult:
        if not image_data:
            return SubAgentResult(agent_name=self.name, content="")

        from langchain_core.messages import HumanMessage
        b64 = base64.b64encode(image_data).decode()
        message = HumanMessage(
            content=[
                {"type": "text", "text": IMAGE_ANALYZER_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
            ]
        )
        try:
            response = await asyncio.to_thread(self._llm.invoke, [message])
            return SubAgentResult(agent_name=self.name, content=response.content or "")
        except Exception as e:
            logger.warning("image_analyzer error: %s", e)
            return SubAgentResult(agent_name=self.name, content="")
