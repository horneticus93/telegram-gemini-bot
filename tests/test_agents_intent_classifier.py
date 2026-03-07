import pytest
from bot.agents.intent_classifier import IntentClassifier

@pytest.fixture
def clf():
    return IntentClassifier()

@pytest.mark.asyncio
async def test_classifies_question(clf):
    result = await clf.run(text="Як справи?")
    assert result.content == "question"

@pytest.mark.asyncio
async def test_classifies_request(clf):
    result = await clf.run(text="Допоможи мені написати лист")
    assert result.content == "request"

@pytest.mark.asyncio
async def test_classifies_other(clf):
    result = await clf.run(text="хаха лол")
    assert result.content == "other"
