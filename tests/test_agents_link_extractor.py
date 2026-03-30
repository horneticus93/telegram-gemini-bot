import pytest
from unittest.mock import MagicMock
from bot.agents.link_extractor import LinkExtractor


@pytest.fixture
def llm_ok():
    llm = MagicMock()
    msg = MagicMock()
    msg.content = "Стаття про Python 3.13 з новими фічами."
    llm.invoke = MagicMock(return_value=msg)
    return llm


@pytest.mark.asyncio
async def test_extracts_links(llm_ok):
    agent = LinkExtractor(llm=llm_ok, max_links=3)
    result = await agent.run(text="Дивись https://python.org та https://docs.python.org")
    assert result.metadata["links_found"] == 2
    assert "Python" in result.content or result.content != ""


@pytest.mark.asyncio
async def test_no_links_returns_empty(llm_ok):
    agent = LinkExtractor(llm=llm_ok, max_links=3)
    result = await agent.run(text="просто текст без посилань")
    assert result.content == ""
    assert result.metadata["links_found"] == 0
