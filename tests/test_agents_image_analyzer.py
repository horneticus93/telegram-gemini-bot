import pytest
from unittest.mock import MagicMock
from bot.agents.image_analyzer import ImageAnalyzer


@pytest.fixture
def llm_ok():
    llm = MagicMock()
    msg = MagicMock()
    msg.content = "Фото з котом на дивані."
    llm.invoke = MagicMock(return_value=msg)
    return llm


@pytest.mark.asyncio
async def test_analyzes_image_bytes(llm_ok):
    agent = ImageAnalyzer(llm=llm_ok)
    result = await agent.run(image_data=b"fakebytes", mime_type="image/jpeg")
    assert "кот" in result.content.lower() or "фото" in result.content.lower()
    assert result.agent_name == "image_analyzer"


@pytest.mark.asyncio
async def test_returns_empty_on_no_data(llm_ok):
    agent = ImageAnalyzer(llm=llm_ok)
    result = await agent.run(image_data=b"", mime_type="image/jpeg")
    assert result.content == ""
