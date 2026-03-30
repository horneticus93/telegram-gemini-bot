import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from bot.tools import execute_tool, TOOL_DEFINITIONS

@pytest.mark.asyncio
async def test_memory_add_calls_merge_and_embed():
    graph = AsyncMock()
    graph.merge_node = AsyncMock(return_value=42)
    embeddings = AsyncMock()
    embeddings.save = AsyncMock()

    result = await execute_tool(
        "memory_add",
        {"subject": "Oleh", "relation": "LIVES_IN", "object": "Berlin",
         "subject_type": "Person", "object_type": "Place"},
        graph=graph, embeddings=embeddings,
    )
    graph.merge_node.assert_called()
    assert "saved" in result.lower()

@pytest.mark.asyncio
async def test_memory_search_returns_formatted():
    embeddings = AsyncMock()
    embeddings.search_text = AsyncMock(return_value=[1, 2])
    graph = AsyncMock()
    graph.search_by_ids = AsyncMock(return_value=[{"name": "Oleh"}, {"name": "Berlin"}])

    result = await execute_tool(
        "memory_search",
        {"query": "where does Oleh live"},
        graph=graph, embeddings=embeddings,
    )
    assert "Oleh" in result

@pytest.mark.asyncio
async def test_memory_delete_removes_node():
    graph = AsyncMock()
    graph.delete_node = AsyncMock()
    result = await execute_tool(
        "memory_delete",
        {"node_id": 42},
        graph=graph, embeddings=AsyncMock(),
    )
    graph.delete_node.assert_called_once_with(42)
    assert "deleted" in result.lower()

@pytest.mark.asyncio
async def test_web_search_calls_tavily():
    with patch("tavily.AsyncTavilyClient") as MockClient:
        mock_instance = AsyncMock()
        MockClient.return_value = mock_instance
        mock_instance.search = AsyncMock(return_value={
            "results": [{"title": "Berlin", "content": "Capital of Germany", "url": "https://example.com"}]
        })
        result = await execute_tool(
            "web_search",
            {"query": "Berlin"},
            graph=AsyncMock(), embeddings=AsyncMock(),
            tavily_key="fake_key",
        )
    assert "Berlin" in result

def test_tool_definitions_schema():
    names = {t["function"]["name"] for t in TOOL_DEFINITIONS}
    assert {"memory_add", "memory_search", "memory_delete", "memory_get_context", "web_search"} == names
