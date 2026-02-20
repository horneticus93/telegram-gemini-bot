from collections import deque


class SessionManager:
    def __init__(self, max_messages: int = 100):
        self.max_messages = max_messages
        self._sessions: dict[int, deque] = {}

    def add_message(self, chat_id: int, role: str, text: str) -> None:
        """Add a message to the session.

        Args:
            chat_id: Telegram chat ID.
            role: ``"user"`` for human messages, ``"model"`` for bot replies.
            text: The message content.
        """
        if chat_id not in self._sessions:
            self._sessions[chat_id] = deque(maxlen=self.max_messages)
        self._sessions[chat_id].append({"role": role, "text": text})

    def get_history(self, chat_id: int) -> list[dict]:
        """Return the raw structured history for a chat."""
        if chat_id not in self._sessions:
            return []
        return list(self._sessions[chat_id])

    def format_history(self, chat_id: int) -> str:
        """Return a flat text representation (used by extract_profile)."""
        entries = self.get_history(chat_id)
        label = {"user": "user", "model": "bot"}
        return "\n".join(
            f"[{label.get(e['role'], e['role'])}]: {e['text']}" for e in entries
        )
