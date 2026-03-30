import json
import base64
from typing import Callable, Awaitable
from bot.processor import ProcessedMessage
from bot.session import SessionManager


class ContextBuilder:
    def __init__(
        self,
        session: SessionManager,
        memory_search: Callable[[str, int], Awaitable[list[dict]]],
        settings,
    ) -> None:
        self._session = session
        self._memory_search = memory_search
        self._settings = settings

    async def build(self, chat_id: int, processed: ProcessedMessage) -> list[dict]:
        """Build the messages list for LiteLLM from session + memory + current message."""
        system_parts: list[str] = []

        # System prompt
        system_prompt = await self._settings.get("system_prompt", default="You are a helpful assistant.")
        system_parts.append(system_prompt if isinstance(system_prompt, str) else "You are a helpful assistant.")

        # Summary
        summary = self._session.get_summary(chat_id)
        if summary:
            system_parts.append(f"\n\n[Conversation summary]\n{summary}")

        # Relevant memories
        if processed.text:
            limit = await self._settings.get("memory_search_limit", default=5)
            memories = await self._memory_search(processed.text, limit)
            if memories:
                mem_lines = "\n".join(f"- {json.dumps(m)}" for m in memories)
                system_parts.append(f"\n\n[Relevant memories]\n{mem_lines}")

        messages: list[dict] = [
            {"role": "system", "content": "\n".join(system_parts)}
        ]

        # Recent history
        max_hist = await self._settings.get("max_history_messages", default=50)
        for entry in self._session.get_recent(chat_id, n=max_hist):
            messages.append({"role": entry["role"], "content": entry["text"]})

        # Current message — build content blocks (possibly multimodal)
        user_content = _build_user_content(processed)
        messages.append({"role": "user", "content": user_content})

        return messages


def _build_user_content(processed: ProcessedMessage):
    """Build LiteLLM content for the current message (text, image, or mixed)."""
    prefix_parts = []
    if processed.forward_meta:
        prefix_parts.append(processed.forward_meta)
    if processed.fetched_urls:
        for url, content in processed.fetched_urls.items():
            prefix_parts.append(f"[Content from {url}]:\n{content}")
    prefix = "\n\n".join(prefix_parts)

    text = (prefix + "\n\n" + (processed.text or "")).strip() if prefix else (processed.text or "")

    if processed.image_bytes and text:
        img_b64 = base64.b64encode(processed.image_bytes).decode()
        return [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
        ]
    elif processed.image_bytes:
        img_b64 = base64.b64encode(processed.image_bytes).decode()
        return [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}]
    else:
        return text or "(no text)"
