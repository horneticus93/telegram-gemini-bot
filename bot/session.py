from collections import deque


class SessionManager:
    def __init__(self, max_messages: int = 50, recent_window: int = 15):
        self.max_messages = max_messages
        self.recent_window = recent_window
        self._sessions: dict[int, deque] = {}
        self._summaries: dict[int, str] = {}
        self._summarized_count: dict[int, int] = {}

    def add_message(self, chat_id: int, role: str, text: str, author: str | None = None) -> None:
        """Add a message to the session.

        Args:
            chat_id: Telegram chat ID.
            role: ``"user"`` for human messages, ``"model"`` for bot replies.
            text: The message content.
            author: Optional display name of the human user.
        """
        if chat_id not in self._sessions:
            self._sessions[chat_id] = deque(maxlen=self.max_messages)
        self._sessions[chat_id].append({"role": role, "text": text, "author": author})

    def get_history(self, chat_id: int) -> list[dict]:
        """Return the full message history for a chat."""
        if chat_id not in self._sessions:
            return []
        return list(self._sessions[chat_id])

    def get_recent(self, chat_id: int) -> list[dict]:
        """Return the last ``recent_window`` messages for a chat."""
        history = self.get_history(chat_id)
        return history[-self.recent_window:]

    def get_unsummarized(self, chat_id: int) -> list[dict]:
        """Return messages that have not yet been summarized."""
        history = self.get_history(chat_id)
        offset = self._summarized_count.get(chat_id, 0)
        return history[offset:]

    def mark_summarized(self, chat_id: int, count: int) -> None:
        """Advance the summarization pointer by ``count`` messages."""
        current = self._summarized_count.get(chat_id, 0)
        self._summarized_count[chat_id] = current + count

    def get_summary(self, chat_id: int) -> str:
        """Return the running summary for a chat, or empty string if none."""
        return self._summaries.get(chat_id, "")

    def set_summary(self, chat_id: int, summary: str) -> None:
        """Store a running summary for a chat."""
        self._summaries[chat_id] = summary

    def needs_summary(self, chat_id: int, threshold: int = 30) -> bool:
        """Return True if the number of unsummarized messages meets the threshold."""
        return len(self.get_unsummarized(chat_id)) >= threshold

    def format_history(self, chat_id: int) -> str:
        """Return a flat text representation suitable for summarization prompts."""
        entries = self.get_history(chat_id)
        return "\n".join(
            f"[{e['author'] or 'user'}]: {e['text']}" if e["role"] == "user"
            else f"[bot]: {e['text']}"
            for e in entries
        )
