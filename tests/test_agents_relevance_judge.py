import pytest
from unittest.mock import MagicMock
from bot.agents.relevance_judge import RelevanceJudge
from bot.agents.base import SubAgentResult


@pytest.fixture
def llm_filter():
    llm = MagicMock()
    msg = MagicMock()
    msg.content = '["memory_retriever"]'
    llm.invoke = MagicMock(return_value=msg)
    return llm


@pytest.mark.asyncio
async def test_filters_irrelevant_agents(llm_filter):
    agent = RelevanceJudge(llm=llm_filter)
    results = [
        SubAgentResult(agent_name="memory_retriever", content="Іван любить каву"),
        SubAgentResult(agent_name="context_analyst", content="тон нейтральний"),
    ]
    filtered = await agent.run(text="Що Іван п'є?", sub_agent_results=results)
    assert len(filtered) == 1
    assert filtered[0].agent_name == "memory_retriever"
