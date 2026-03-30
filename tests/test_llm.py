# tests/test_llm.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bot.llm import LLMService

def make_settings(**overrides):
    s = AsyncMock()
    defaults = {
        "chat_model": "gemini/gemini-2.5-pro",
        "vision_model": "gemini/gemini-2.0-flash",
        "tavily_api_key": None,
    }
    defaults.update(overrides)
    s.get = AsyncMock(side_effect=lambda k, **kw: defaults.get(k, kw.get("default")))
    return s

def make_litellm_response(content="Hello!", tool_calls=None):
    choice = MagicMock()
    choice.message.content = content
    choice.message.tool_calls = tool_calls or []
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = MagicMock(total_tokens=42, prompt_tokens=10, completion_tokens=32)
    resp.model = "gemini/gemini-2.5-pro"
    return resp

@pytest.mark.asyncio
async def test_simple_text_response():
    svc = LLMService(settings=make_settings(), graph=AsyncMock(), embeddings=AsyncMock())
    messages = [{"role": "user", "content": "hello"}]
    with patch("litellm.acompletion", AsyncMock(return_value=make_litellm_response("Hello!"))):
        result = await svc.complete(messages, has_image=False)
    assert result.text == "Hello!"

@pytest.mark.asyncio
async def test_uses_vision_model_for_images():
    captured = {}
    async def mock_completion(**kwargs):
        captured["model"] = kwargs["model"]
        return make_litellm_response("I see a cat.")
    svc = LLMService(settings=make_settings(), graph=AsyncMock(), embeddings=AsyncMock())
    messages = [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:..."}}]}]
    with patch("litellm.acompletion", mock_completion):
        await svc.complete(messages, has_image=True)
    assert captured["model"] == "gemini/gemini-2.0-flash"

@pytest.mark.asyncio
async def test_tool_call_is_executed():
    tool_call = MagicMock()
    tool_call.function.name = "memory_search"
    tool_call.function.arguments = '{"query": "test"}'
    tool_call.id = "call_1"

    call_count = 0
    async def mock_completion(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return make_litellm_response(content=None, tool_calls=[tool_call])
        return make_litellm_response("Based on memory: ...")

    svc = LLMService(settings=make_settings(), graph=AsyncMock(), embeddings=AsyncMock())
    with patch("litellm.acompletion", mock_completion):
        with patch("bot.llm.execute_tool", AsyncMock(return_value="Memory result")):
            result = await svc.complete([{"role": "user", "content": "who am I"}], has_image=False)
    assert call_count == 2
    assert "Based on memory" in result.text
