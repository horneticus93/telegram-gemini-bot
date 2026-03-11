import pytest
from unittest.mock import MagicMock
from bot.agents.repost_analyzer import RepostAnalyzer


@pytest.fixture
def llm_ok():
    llm = MagicMock()
    msg = MagicMock()
    msg.content = '{"summary": "Новина про відключення світла.", "source": "Новини України"}'
    llm.invoke = MagicMock(return_value=msg)
    return llm


@pytest.mark.asyncio
async def test_analyzes_repost(llm_ok):
    agent = RepostAnalyzer(llm=llm_ok)
    result = await agent.run(forwarded_text="Увага! З 20:00 відключення світла.", forward_from="Новини України")
    assert "відключення" in result.content.lower() or result.content != ""
    assert result.metadata.get("source") == "Новини України"


@pytest.mark.asyncio
async def test_empty_text_returns_empty(llm_ok):
    agent = RepostAnalyzer(llm=llm_ok)
    result = await agent.run(forwarded_text="", forward_from=None)
    assert result.content == ""
