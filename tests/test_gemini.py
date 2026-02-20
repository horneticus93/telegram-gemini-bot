import pytest
from unittest.mock import MagicMock, patch
from bot.gemini import GeminiClient


@patch("bot.gemini.genai.Client")
def test_ask_calls_generate_content(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = "Paris is the capital of France."
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    result = client.ask(history="[Alice]: What's the capital of France?", question="What's the capital of France?")

    assert result == "Paris is the capital of France."
    mock_client.models.generate_content.assert_called_once()


@patch("bot.gemini.genai.Client")
def test_ask_includes_history_in_prompt(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = "Some answer"
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    client.ask(history="[Alice]: test history", question="test question")

    call_kwargs = mock_client.models.generate_content.call_args
    contents = call_kwargs.kwargs.get("contents") or call_kwargs.args[1]
    assert "[Alice]: test history" in contents
    assert "test question" in contents


@patch("bot.gemini.genai.Client")
def test_ask_with_empty_history(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = "Hello!"
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    result = client.ask(history="", question="Say hello")

    assert result == "Hello!"
    call_kwargs = mock_client.models.generate_content.call_args
    contents = call_kwargs.kwargs["contents"]
    assert contents == "Say hello"  # bare question, no history wrapper


@patch("bot.gemini.genai.Client")
def test_ask_raises_on_none_response(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = None
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    with pytest.raises(ValueError, match="no text response"):
        client.ask(history="", question="test")


@patch("bot.gemini.genai.Client")
def test_ask_includes_user_profile_in_prompt(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = "Answer"
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    client.ask(history="", question="What should I eat?", user_profile="Alice loves Italian food.")

    call_kwargs = mock_client.models.generate_content.call_args
    contents = call_kwargs.kwargs.get("contents") or call_kwargs.args[1]
    assert "Alice loves Italian food." in contents


@patch("bot.gemini.genai.Client")
def test_ask_without_profile_omits_profile_section(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = "Answer"
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    client.ask(history="", question="Hello", user_profile="", chat_members=[])

    call_kwargs = mock_client.models.generate_content.call_args
    contents = call_kwargs.kwargs.get("contents") or call_kwargs.args[1]
    assert "Profile" not in contents
    assert "Members" not in contents


@patch("bot.gemini.genai.Client")
def test_ask_includes_chat_members_in_prompt(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = "Answer"
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    client.ask(history="", question="Who's here?", user_profile="", chat_members=["Alice", "Bob"])

    call_kwargs = mock_client.models.generate_content.call_args
    contents = call_kwargs.kwargs.get("contents") or call_kwargs.args[1]
    assert "Alice" in contents
    assert "Bob" in contents


@patch("bot.gemini.genai.Client")
def test_extract_profile_returns_text(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = "Alice is a nurse who likes hiking."
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    result = client.extract_profile(
        existing_profile="",
        recent_history="[Alice]: I just got back from a hike",
        user_name="Alice",
    )
    assert result == "Alice is a nurse who likes hiking."
    mock_client.models.generate_content.assert_called_once()
