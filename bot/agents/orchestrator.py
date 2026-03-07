"""AgentOrchestrator — runs sub-agents and builds pre-context brief."""
from __future__ import annotations
import asyncio
import logging

from .base import SubAgentResult
from .mention_detector import MentionDetector
from .memory_retriever import MemoryRetriever
from .context_analyst import ContextAnalyst
from .image_analyzer import ImageAnalyzer
from .link_extractor import URL_RE, LinkExtractor
from .repost_analyzer import RepostAnalyzer

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    def __init__(
        self,
        *,
        mention_detector: MentionDetector,
        memory_retriever: MemoryRetriever,
        context_analyst: ContextAnalyst,
        image_analyzer: ImageAnalyzer | None,
        link_extractor: LinkExtractor | None,
        repost_analyzer: RepostAnalyzer | None,
        memory,
    ):
        self._mention = mention_detector
        self._memory_retriever = memory_retriever
        self._context = context_analyst
        self._image = image_analyzer
        self._links = link_extractor
        self._repost = repost_analyzer
        self._memory = memory

    async def build_pre_context(
        self,
        *,
        text: str,
        chat_id: int,
        recent_messages: list[dict],
        has_photo: bool,
        has_forward: bool,
        image_data: bytes | None = None,
        mime_type: str = "image/jpeg",
        forwarded_text: str = "",
        forward_from: str | None = None,
        subagent_timeout: float = 8.0,
    ) -> str:
        """Run all applicable sub-agents and return a formatted pre-context string."""
        bot_aliases = await asyncio.to_thread(self._memory.get_bot_aliases, chat_id)

        # Always-on agents
        always_on_coros = [
            self._mention.run(text=text, bot_aliases=bot_aliases, chat_id=chat_id),
            self._memory_retriever.run(text=text),
            self._context.run(recent_messages=recent_messages),
        ]

        # Conditional agents
        conditional_coros = []
        if has_photo and self._image and image_data:
            conditional_coros.append(self._image.run(image_data=image_data, mime_type=mime_type))
        if self._links and URL_RE.search(text):
            conditional_coros.append(self._links.run(text=text))
        if has_forward and self._repost:
            conditional_coros.append(self._repost.run(forwarded_text=forwarded_text, forward_from=forward_from))

        async def safe_run(coro):
            try:
                return await asyncio.wait_for(coro, timeout=subagent_timeout)
            except asyncio.TimeoutError:
                logger.warning("Sub-agent timed out")
                return None
            except Exception as e:
                logger.warning("Sub-agent error: %s", e)
                return None

        all_coros = always_on_coros + conditional_coros
        raw_results = await asyncio.gather(*[safe_run(c) for c in all_coros])
        results: list[SubAgentResult] = [r for r in raw_results if r is not None]

        # Handle new bot alias discovery
        for r in results:
            if r.agent_name == "mention_detector":
                new_alias = r.metadata.get("new_alias")
                if new_alias:
                    await asyncio.to_thread(self._memory.add_bot_alias, chat_id, new_alias)
                break

        return self._format_brief(results)

    def _format_brief(self, results: list[SubAgentResult]) -> str:
        sections: list[str] = []
        for r in results:
            if not r.content:
                continue
            sections.append(f"[{r.agent_name}]\n{r.content}")
        if not sections:
            return ""
        return "\n\n".join(sections)
