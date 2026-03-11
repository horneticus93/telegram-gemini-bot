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

@pytest.mark.asyncio
async def test_simple_smalltalk_is_simple(clf):
    result = await clf.run(text="хаха лол")
    assert result.metadata["complexity"] == "simple"

@pytest.mark.asyncio
async def test_short_question_is_simple(clf):
    result = await clf.run(text="Як справи?")
    assert result.metadata["complexity"] == "simple"

@pytest.mark.asyncio
async def test_photo_forces_complex(clf):
    result = await clf.run(text="глянь", has_photo=True)
    assert result.metadata["complexity"] == "complex"

@pytest.mark.asyncio
async def test_url_forces_complex(clf):
    result = await clf.run(text="подивись", has_url=True)
    assert result.metadata["complexity"] == "complex"

@pytest.mark.asyncio
async def test_forward_forces_complex(clf):
    result = await clf.run(text="що думаєш?", has_forward=True)
    assert result.metadata["complexity"] == "complex"

@pytest.mark.asyncio
async def test_request_intent_is_complex(clf):
    result = await clf.run(text="Допоможи мені написати лист")
    assert result.metadata["complexity"] == "complex"

@pytest.mark.asyncio
async def test_long_text_is_complex(clf):
    result = await clf.run(text="а" * 151)
    assert result.metadata["complexity"] == "complex"

@pytest.mark.asyncio
async def test_technical_keyword_ua_is_complex(clf):
    result = await clf.run(text="поясни цей алгоритм")
    assert result.metadata["complexity"] == "complex"

@pytest.mark.asyncio
async def test_technical_keyword_en_is_complex(clf):
    result = await clf.run(text="explain this code")
    assert result.metadata["complexity"] == "complex"

@pytest.mark.asyncio
async def test_technical_keyword_ru_is_complex(clf):
    result = await clf.run(text="объясни этот код")
    assert result.metadata["complexity"] == "complex"

@pytest.mark.asyncio
async def test_web_trigger_ua_is_complex(clf):
    result = await clf.run(text="яка погода сьогодні?")
    assert result.metadata["complexity"] == "complex"

@pytest.mark.asyncio
async def test_web_trigger_en_is_complex(clf):
    result = await clf.run(text="what is the weather today?")
    assert result.metadata["complexity"] == "complex"

@pytest.mark.asyncio
async def test_web_trigger_ru_is_complex(clf):
    result = await clf.run(text="какая погода сегодня?")
    assert result.metadata["complexity"] == "complex"
