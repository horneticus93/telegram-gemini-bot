import pytest
from unittest.mock import MagicMock
from bot.agents.memory_retriever import MemoryRetriever
from bot.agents.base import SubAgentResult


@pytest.fixture
def mock_memory():
    mem = MagicMock()
    mem.search_memories.return_value = [
        {"id": 1, "content": "Олег любить каву", "importance": 0.8, "score": 0.9}
    ]
    return mem


@pytest.fixture
def mock_embed():
    return lambda text: [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_retrieves_memories(mock_memory, mock_embed):
    agent = MemoryRetriever(memory=mock_memory, embed_fn=mock_embed, top_k=5)
    result = await agent.run(text="Що Олег п'є?")
    assert "Олег любить каву" in result.content
    assert result.metadata["count"] == 1


@pytest.mark.asyncio
async def test_returns_empty_when_no_memories(mock_embed):
    mem = MagicMock()
    mem.search_memories.return_value = []
    agent = MemoryRetriever(memory=mem, embed_fn=mock_embed, top_k=5)
    result = await agent.run(text="щось")
    assert result.content == ""
    assert result.metadata["count"] == 0
