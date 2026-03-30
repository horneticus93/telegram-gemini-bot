from collections import deque
import litellm


class SessionManager:
    def __init__(self, settings=None, max_history: int = 50, recent_window: int = 15, max_messages: int | None = None) -> None:
        self._settings = settings
        # max_messages is an alias for max_history (legacy compat)
        self._max_history = max_messages if max_messages is not None else max_history
        self.recent_window = recent_window
        self._sessions: dict[int, deque] = {}
        self._summaries: dict[int, str] = {}
        self._summarized_count: dict[int, int] = {}
        self._memory_watched_count: dict[int, int] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_deque(self, chat_id: int) -> deque:
        if chat_id not in self._sessions:
            self._sessions[chat_id] = deque(maxlen=self._max_history)
        return self._sessions[chat_id]

    # ------------------------------------------------------------------
    # Message storage
    # ------------------------------------------------------------------

    def add_message(self, chat_id: int, role: str, text: str, author: str | None = None) -> None:
        """Add a message to the session.

        Args:
            chat_id: Telegram chat ID.
            role: ``"user"`` for human messages, ``"model"``/``"assistant"`` for bot replies.
            text: The message content.
            author: Optional display name of the human user.
        """
        dq = self._get_deque(chat_id)
        dq.append({"role": role, "text": text, "author": author})

    def get_history(self, chat_id: int) -> list[dict]:
        """Return the full message history for a chat."""
        if chat_id not in self._sessions:
            return []
        return list(self._sessions[chat_id])

    def get_recent(self, chat_id: int, n: int | None = None) -> list[dict]:
        """Return recent messages for a chat.

        If ``n`` is given, return the last ``n`` messages.
        Otherwise return the last ``recent_window`` messages.
        """
        history = self.get_history(chat_id)
        window = n if n is not None else self.recent_window
        return history[-window:] if history else []

    # ------------------------------------------------------------------
    # Summarization tracking
    # ------------------------------------------------------------------

    def get_unsummarized(self, chat_id: int) -> list[dict]:
        """Return messages that have not yet been summarized."""
        history = self.get_history(chat_id)
        offset = self._summarized_count.get(chat_id, 0)
        return history[offset:]

    def mark_summarized(self, chat_id: int, count: int) -> None:
        """Advance the summarization pointer by ``count`` messages."""
        current = self._summarized_count.get(chat_id, 0)
        self._summarized_count[chat_id] = current + count

    def needs_summary(self, chat_id: int, threshold: int = 30) -> bool:
        """Return True if the number of unsummarized messages meets the threshold."""
        return len(self.get_unsummarized(chat_id)) >= threshold

    def unsummarized_count(self, chat_id: int) -> int:
        """Return number of unsummarized messages for this chat."""
        return len(self.get_unsummarized(chat_id))

    def get_summary(self, chat_id: int) -> str | None:
        """Return the running summary for a chat, or None if none."""
        return self._summaries.get(chat_id)

    def set_summary(self, chat_id: int, summary: str) -> None:
        """Store a running summary for a chat."""
        self._summaries[chat_id] = summary

    # ------------------------------------------------------------------
    # Memory-watch tracking
    # ------------------------------------------------------------------

    def get_unwatched(self, chat_id: int) -> list[dict]:
        """Return messages that have not yet been processed by memory_watcher."""
        history = self.get_history(chat_id)
        offset = self._memory_watched_count.get(chat_id, 0)
        return history[offset:]

    def mark_memory_watched(self, chat_id: int, count: int) -> None:
        """Advance the memory-watch pointer by ``count`` messages."""
        current = self._memory_watched_count.get(chat_id, 0)
        self._memory_watched_count[chat_id] = current + count

    def needs_memory_watch(self, chat_id: int, threshold: int) -> bool:
        """Return True if the number of unwatched messages meets the threshold."""
        return len(self.get_unwatched(chat_id)) >= threshold

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def format_history(self, chat_id: int) -> str:
        """Return a flat text representation suitable for summarization prompts."""
        entries = self.get_history(chat_id)
        return "\n".join(
            f"[{e['author'] or 'user'}]: {e['text']}" if e["role"] == "user"
            else f"[bot]: {e['text']}"
            for e in entries
        )

    # ------------------------------------------------------------------
    # Async summarization
    # ------------------------------------------------------------------

    async def maybe_summarize(self, chat_id: int) -> None:
        """Summarize session history if threshold exceeded."""
        threshold = await self._settings.get("summary_threshold", default=30)
        if len(self.get_unsummarized(chat_id)) < threshold:
            return
        model = await self._settings.get("summarization_model")
        max_words = await self._settings.get("summary_max_words", default=500)
        history = self.get_recent(chat_id)
        messages_text = "\n".join(
            f"{m['author']}: {m['text']}" for m in history
        )
        prev_summary = self.get_summary(chat_id) or ""
        prompt = (
            f"Previous summary:\n{prev_summary}\n\n"
            f"New messages:\n{messages_text}\n\n"
            f"Write a concise summary in under {max_words} words."
        )
        response = await litellm.acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        summary = response.choices[0].message.content
        self.set_summary(chat_id, summary)
        # Reload max_history from settings and resize deque if needed
        new_max = await self._settings.get("max_history_messages", default=50)
        self._max_history = new_max
        dq = self._get_deque(chat_id)
        self._sessions[chat_id] = deque(dq, maxlen=new_max)
