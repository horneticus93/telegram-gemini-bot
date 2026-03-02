from typing import Annotated, Sequence, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class BotState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    chat_id: int
    user_name: str
    user_id: int
    bot_username: str
    question: str
    summary: str
    should_respond: bool
    response_text: str
    used_memory_ids: list[int]
