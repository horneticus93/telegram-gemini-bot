import pytest
from unittest.mock import MagicMock
from bot.agents.mention_detector import MentionDetector

@pytest.fixture
def llm_yes():
    """LLM that returns JSON indicating bot is addressed."""
    llm = MagicMock()
    msg = MagicMock()
    msg.content = '{"is_addressed": true, "confidence": 0.9, "new_alias": "Гена"}'
    llm.invoke = MagicMock(return_value=msg)
    return llm

@pytest.fixture
def llm_no():
    llm = MagicMock()
    msg = MagicMock()
    msg.content = '{"is_addressed": false, "confidence": 0.95, "new_alias": null}'
    llm.invoke = MagicMock(return_value=msg)
    return llm

@pytest.mark.asyncio
async def test_detects_addressed(llm_yes):
    agent = MentionDetector(llm=llm_yes, confidence_threshold=0.7)
    result = await agent.run(text="Гена, як справи?", bot_aliases=[], chat_id=1)
    assert result.metadata["is_addressed"] is True
    assert result.metadata["new_alias"] == "Гена"

@pytest.mark.asyncio
async def test_not_addressed(llm_no):
    agent = MentionDetector(llm=llm_no, confidence_threshold=0.7)
    result = await agent.run(text="привіт всім", bot_aliases=[], chat_id=1)
    assert result.metadata["is_addressed"] is False

@pytest.mark.asyncio
async def test_low_confidence_treated_as_not_addressed(llm_yes):
    """When LLM says yes but confidence < threshold, treat as not addressed."""
    llm = MagicMock()
    msg = MagicMock()
    msg.content = '{"is_addressed": true, "confidence": 0.3, "new_alias": null}'
    llm.invoke = MagicMock(return_value=msg)
    agent = MentionDetector(llm=llm, confidence_threshold=0.7)
    result = await agent.run(text="хтось щось", bot_aliases=[], chat_id=1)
    assert result.metadata["is_addressed"] is False
