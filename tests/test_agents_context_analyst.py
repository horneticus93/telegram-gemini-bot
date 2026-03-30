import pytest
from unittest.mock import MagicMock
from bot.agents.context_analyst import ContextAnalyst


@pytest.fixture
def llm_ok():
    llm = MagicMock()
    msg = MagicMock()
    msg.content = '{"tone": "positive", "main_topics": ["спорт"], "active_participants": ["Іван"], "summary": "Говорили про спорт."}'
    llm.invoke = MagicMock(return_value=msg)
    return llm


@pytest.mark.asyncio
async def test_returns_analysis(llm_ok):
    agent = ContextAnalyst(llm=llm_ok)
    messages = [{"author": "Іван", "role": "user", "text": "Дивись яка гра!"}]
    result = await agent.run(recent_messages=messages)
    assert result.metadata["tone"] == "positive"
    assert "спорт" in result.metadata["main_topics"]
    assert "Говорили про спорт." in result.content


@pytest.mark.asyncio
async def test_handles_bad_json(llm_ok):
    llm = MagicMock()
    msg = MagicMock()
    msg.content = "not json at all"
    llm.invoke = MagicMock(return_value=msg)
    agent = ContextAnalyst(llm=llm)
    result = await agent.run(recent_messages=[])
    assert result.content == ""
