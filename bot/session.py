from collections import deque


class SessionManager:
    def __init__(self, max_messages: int = 100):
        self.max_messages = max_messages
        self._sessions: dict[int, deque] = {}

    def add_message(self, chat_id: int, author: str, text: str) -> None:
        if chat_id not in self._sessions:
            self._sessions[chat_id] = deque(maxlen=self.max_messages)
        self._sessions[chat_id].append(f"[{author}]: {text}")

    def get_history(self, chat_id: int) -> list[str]:
        if chat_id not in self._sessions:
            return []
        return list(self._sessions[chat_id])

    def format_history(self, chat_id: int) -> str:
        return "\n".join(self.get_history(chat_id))
