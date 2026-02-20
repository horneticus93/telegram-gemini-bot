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
    result = client.ask(history=[], question="What's the capital of France?")

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
    client.ask(
        history=[{"role": "user", "text": "test history"}],
        question="test question",
    )

    call_kwargs = mock_client.models.generate_content.call_args
    contents = call_kwargs.kwargs.get("contents") or call_kwargs.args[1]
    # contents is now a list of types.Content objects
    all_texts = " ".join(part.text for c in contents for part in c.parts)
    assert "test history" in all_texts
    assert "test question" in all_texts


@patch("bot.gemini.genai.Client")
def test_ask_with_empty_history(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = "Hello!"
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    result = client.ask(history=[], question="Say hello")

    assert result == "Hello!"
    call_kwargs = mock_client.models.generate_content.call_args
    contents = call_kwargs.kwargs["contents"]
    # With no history and no context, only the question turn is present
    assert len(contents) == 1
    assert contents[0].parts[0].text == "Say hello"


@patch("bot.gemini.genai.Client")
def test_ask_raises_on_none_response(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = None
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    with pytest.raises(ValueError, match="no text response"):
        client.ask(history=[], question="test")


@patch("bot.gemini.genai.Client")
def test_ask_includes_user_profile_in_prompt(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = "Answer"
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    client.ask(history=[], question="What should I eat?", user_profile="Alice loves Italian food.")

    call_kwargs = mock_client.models.generate_content.call_args
    contents = call_kwargs.kwargs.get("contents") or call_kwargs.args[1]
    all_texts = " ".join(part.text for c in contents for part in c.parts)
    assert "Alice loves Italian food." in all_texts


@patch("bot.gemini.genai.Client")
def test_ask_without_profile_omits_profile_section(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = "Answer"
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    client.ask(history=[], question="Hello", user_profile="", chat_members=[])

    call_kwargs = mock_client.models.generate_content.call_args
    contents = call_kwargs.kwargs.get("contents") or call_kwargs.args[1]
    all_texts = " ".join(part.text for c in contents for part in c.parts)
    assert "Profile" not in all_texts
    assert "Members" not in all_texts


@patch("bot.gemini.genai.Client")
def test_ask_includes_chat_members_in_prompt(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = "Answer"
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    client.ask(history=[], question="Who's here?", user_profile="", chat_members=["Alice", "Bob"])

    call_kwargs = mock_client.models.generate_content.call_args
    contents = call_kwargs.kwargs.get("contents") or call_kwargs.args[1]
    all_texts = " ".join(part.text for c in contents for part in c.parts)
    assert "Alice" in all_texts
    assert "Bob" in all_texts


@patch("bot.gemini.genai.Client")
def test_ask_history_roles_are_preserved(mock_client_cls):
    """Gemini should receive separate user and model turns, not a flat blob."""
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = "Sure!"
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    client.ask(
        history=[
            {"role": "user", "text": "Hello"},
            {"role": "model", "text": "Hi there!"},
        ],
        question="How are you?",
    )

    call_kwargs = mock_client.models.generate_content.call_args
    contents = call_kwargs.kwargs.get("contents") or call_kwargs.args[1]
    roles = [c.role for c in contents]
    # user, model from history + user for the current question
    assert roles == ["user", "model", "user"]


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
        recent_history="[user]: I just got back from a hike",
        user_name="Alice",
    )
    assert result == "Alice is a nurse who likes hiking."
    mock_client.models.generate_content.assert_called_once()
