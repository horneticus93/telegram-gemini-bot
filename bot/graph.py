"""LangGraph state-graph builder and standalone helper nodes.

``should_respond_node`` and ``build_context_node`` are plain functions
called by handlers before the graph is invoked.  ``build_graph``
assembles the agent/tools loop and returns a compiled graph.
"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from .prompts import SYSTEM_PROMPT
from .state import BotState
from .tools import create_memory_save, create_memory_search, create_web_search


# ---------------------------------------------------------------------------
# Standalone helper functions (used by handlers before invoking graph)
# ---------------------------------------------------------------------------


def should_respond_node(
    state: dict,
    *,
    is_private: bool,
    is_reply_to_bot: bool,
    is_mention: bool,
) -> dict:
    """Decide whether the bot should respond to a message.

    Returns ``{"should_respond": True}`` when any of the three flags is
    ``True``, otherwise ``{"should_respond": False}``.  *state* is
    accepted for interface consistency but is not used.
    """
    return {"should_respond": is_private or is_reply_to_bot or is_mention}


def build_context_node(state: dict, *, recent_messages: list[dict]) -> dict:
    """Build LangChain message list from summary + recent session messages.

    If *state* contains a non-empty ``"summary"`` key a ``HumanMessage``
    with the summary and an ``AIMessage`` acknowledgment are prepended.
    Each entry in *recent_messages* becomes a ``HumanMessage`` (role=user)
    or ``AIMessage`` (role=model) with ``[author]: text`` formatting.
    """
    messages: list[HumanMessage | AIMessage] = []

    summary = state.get("summary", "")
    if summary:
        messages.append(
            HumanMessage(content=f"Summary of earlier conversation: {summary}")
        )
        messages.append(
            AIMessage(content="Got it, I'll keep that context in mind.")
        )

    for msg in recent_messages:
        content = f"[{msg['author']}]: {msg['text']}"
        if msg["role"] == "user":
            messages.append(HumanMessage(content=content))
        else:
            messages.append(AIMessage(content=content))

    return {"messages": messages}


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def _route_after_agent(state: dict) -> str:
    """Conditional edge: go to tools if the last message has tool calls."""
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return END


def build_graph(llm, memory, embed_fn):
    """Assemble and compile the LangGraph agent loop.

    Parameters
    ----------
    llm:
        A LangChain chat model (e.g. ``ChatGoogleGenerativeAI``).
    memory:
        A ``BotMemory`` instance for the memory tools.
    embed_fn:
        A callable that maps text to an embedding vector.

    Returns
    -------
    CompiledGraph
        Ready to ``.invoke()`` with a ``BotState`` dict.
    """
    tools = [
        create_memory_search(memory, embed_fn),
        create_memory_save(memory, embed_fn),
        create_web_search(llm),
    ]

    llm_with_tools = llm.bind_tools(tools)

    def agent_node(state: dict) -> dict:
        sys_msg = SystemMessage(content=SYSTEM_PROMPT)
        response = llm_with_tools.invoke([sys_msg] + list(state["messages"]))
        return {"messages": [response]}

    tool_node = ToolNode(tools)

    graph = StateGraph(BotState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", _route_after_agent)
    graph.add_edge("tools", "agent")

    return graph.compile()
