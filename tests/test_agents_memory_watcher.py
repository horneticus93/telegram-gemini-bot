import pytest
from unittest.mock import MagicMock
from bot.agents.memory_watcher import MemoryWatcher


@pytest.fixture
def llm_with_facts():
    llm = MagicMock()
    msg = MagicMock()
    msg.content = '[{"fact": "Іван живе у Львові", "importance": 0.8}]'
    llm.invoke = MagicMock(return_value=msg)
    return llm


@pytest.fixture
def llm_no_facts():
    llm = MagicMock()
    msg = MagicMock()
    msg.content = '[]'
    llm.invoke = MagicMock(return_value=msg)
    return llm


@pytest.mark.asyncio
async def test_identifies_facts(llm_with_facts):
    mock_memory = MagicMock()
    mock_embed = lambda t: [0.1, 0.2]
    agent = MemoryWatcher(llm=llm_with_facts, memory=mock_memory, embed_fn=mock_embed)
    result = await agent.run(messages=[{"author": "Іван", "role": "user", "text": "Я живу у Львові"}])
    assert result.metadata["saved"] == 1
    mock_memory.save_or_update.assert_called_once()


@pytest.mark.asyncio
async def test_saves_nothing_when_no_facts(llm_no_facts):
    mock_memory = MagicMock()
    mock_embed = lambda t: [0.1]
    agent = MemoryWatcher(llm=llm_no_facts, memory=mock_memory, embed_fn=mock_embed)
    result = await agent.run(messages=[])
    assert result.metadata["saved"] == 0
    mock_memory.save_or_update.assert_not_called()
