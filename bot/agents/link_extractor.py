"""Link extractor sub-agent — fetches and summarizes URLs found in text."""
from __future__ import annotations
import asyncio
import logging
import re

from .base import BaseSubAgent, SubAgentResult
from .prompts import LINK_EXTRACTOR_PROMPT

logger = logging.getLogger(__name__)

URL_RE = re.compile(r"https?://[^\s]+")


class LinkExtractor(BaseSubAgent):
    name = "link_extractor"

    def __init__(self, llm, max_links: int = 3):
        self._llm = llm
        self._max_links = max_links

    async def run(self, *, text: str, **kwargs) -> SubAgentResult:
        urls = URL_RE.findall(text)[: self._max_links]
        if not urls:
            return SubAgentResult(
                agent_name=self.name, content="", metadata={"links_found": 0}
            )

        summaries: list[str] = []
        for url in urls:
            summary = await self._summarize_url(url)
            if summary:
                summaries.append(f"[{url}]: {summary}")

        return SubAgentResult(
            agent_name=self.name,
            content="\n".join(summaries),
            metadata={"links_found": len(urls), "urls": urls},
        )

    async def _summarize_url(self, url: str) -> str:
        from langchain_core.messages import HumanMessage
        prompt = LINK_EXTRACTOR_PROMPT.format(url=url)
        try:
            response = await asyncio.to_thread(
                self._llm.invoke, [HumanMessage(content=prompt)]
            )
            return response.content or ""
        except Exception as e:
            logger.warning("link_extractor error for %s: %s", url, e)
            return ""
