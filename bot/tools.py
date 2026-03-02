"""LangChain tool factories for memory and web search.

Each factory accepts pre-built dependencies (memory store, embedding
function, LLM) and returns a ``@tool``-decorated callable ready for
use in a LangGraph agent.
"""

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from bot.memory import BotMemory


def create_memory_search(memory: BotMemory, embed_fn):
    """Return a LangChain tool that searches bot memory."""

    @tool
    def memory_search(query: str) -> str:
        """Search the bot's memory for relevant facts about people, events, or preferences. Use this when you think you might know something useful about the topic being discussed."""
        embedding = embed_fn(query)
        results = memory.search_memories(
            query_embedding=embedding, limit=5, cooldown_seconds=900
        )
        if not results:
            return "No memories found for this query."
        memory.mark_used([r["id"] for r in results])
        lines = [f"- {r['content']}" for r in results]
        return "\n".join(lines)

    return memory_search


def create_memory_save(memory: BotMemory, embed_fn):
    """Return a LangChain tool that saves a fact to bot memory."""

    @tool
    def memory_save(memory_text: str, importance: float = 0.5) -> str:
        """Save an important fact to the bot's long-term memory. Always include full context: who, where, what. Example: 'Олександр в чаті Програмісти працює в Google з 2023 року'."""
        embedding = embed_fn(memory_text)
        result = memory.save_or_update(
            content=memory_text, embedding=embedding, importance=importance
        )
        return result

    return memory_save


def create_web_search(llm):
    """Return a LangChain tool that performs a Google web search via the LLM."""

    @tool
    def web_search(query: str) -> str:
        """Search the web for current information (weather, news, prices, events). Use this when you need up-to-date data that wouldn't be in your memory."""
        bound = llm.bind_tools([{"google_search": {}}])
        response = bound.invoke(
            [HumanMessage(content=f"Search the web and answer: {query}")]
        )
        return response.content or "No results found."

    return web_search
