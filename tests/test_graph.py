from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from bot.graph import build_context_node, build_graph, should_respond_node


def test_should_respond_private_chat():
    result = should_respond_node(
        {}, is_private=True, is_reply_to_bot=False, is_mention=False
    )
    assert result["should_respond"] is True


def test_should_respond_group_mention():
    result = should_respond_node(
        {}, is_private=False, is_reply_to_bot=False, is_mention=True
    )
    assert result["should_respond"] is True


def test_should_respond_group_reply():
    result = should_respond_node(
        {}, is_private=False, is_reply_to_bot=True, is_mention=False
    )
    assert result["should_respond"] is True


def test_should_respond_group_no_mention():
    result = should_respond_node(
        {}, is_private=False, is_reply_to_bot=False, is_mention=False
    )
    assert result["should_respond"] is False


def test_build_context_includes_summary():
    state = {"summary": "Earlier, people discussed weekend plans."}
    result = build_context_node(
        state,
        recent_messages=[
            {"role": "user", "text": "hey", "author": "Bob"},
        ],
    )
    msgs = result["messages"]
    combined = " ".join(m.content for m in msgs)
    assert "weekend plans" in combined


def test_build_context_without_summary():
    state = {"summary": ""}
    result = build_context_node(
        state,
        recent_messages=[
            {"role": "user", "text": "hello", "author": "Alice"},
        ],
    )
    msgs = result["messages"]
    assert len(msgs) == 1  # just the one recent message, no summary block


def test_build_graph_compiles():
    mock_llm = MagicMock()
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)
    mock_memory = MagicMock()
    mock_embed = MagicMock()
    graph = build_graph(mock_llm, mock_memory, mock_embed)
    assert graph is not None
