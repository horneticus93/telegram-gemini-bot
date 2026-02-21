import pytest
from unittest.mock import MagicMock, patch
from bot.gemini import GeminiClient, SYSTEM_PROMPT, _parse_bot_response


# --- _parse_bot_response unit tests ---

def test_parse_valid_json():
    answer, save = _parse_bot_response('{"answer": "Hello!", "save_to_profile": false}')
    assert answer == "Hello!"
    assert save is False


def test_parse_save_true():
    answer, save = _parse_bot_response('{"answer": "Got it.", "save_to_profile": true}')
    assert answer == "Got it."
    assert save is True


def test_parse_ignores_extra_fields():
    answer, save = _parse_bot_response(
        '{"answer": "Got it.", "save_to_profile": true, "save_to_memory": true}'
    )
    assert answer == "Got it."
    assert save is True


def test_parse_strips_markdown_fences():
    raw = '```json\n{"answer": "Hi", "save_to_profile": false}\n```'
    answer, save = _parse_bot_response(raw)
    assert answer == "Hi"
    assert save is False


def test_parse_fallback_on_invalid_json():
    raw = "Sorry, I couldn't understand that."
    answer, save = _parse_bot_response(raw)
    assert answer == raw
    assert save is False


# --- GeminiClient.ask() tests ---

@patch("bot.gemini.genai.Client")
def test_ask_calls_generate_content(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = '{"answer": "Paris is the capital of France.", "save_to_profile": false}'
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    answer, save = client.ask(history=[], question="What's the capital of France?")

    assert answer == "Paris is the capital of France."
    assert save is False
    mock_client.models.generate_content.assert_called_once()


@patch("bot.gemini.genai.Client")
def test_ask_includes_history_in_prompt(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = '{"answer": "Some answer", "save_to_profile": false}'
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    client.ask(
        history=[{"role": "user", "text": "test history"}],
        question="test question",
    )

    call_kwargs = mock_client.models.generate_content.call_args
    contents = call_kwargs.kwargs.get("contents") or call_kwargs.args[1]
    all_texts = " ".join(part.text for c in contents for part in c.parts)
    assert "test history" in all_texts
    assert "test question" in all_texts


@patch("bot.gemini.genai.Client")
def test_ask_with_empty_history(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = '{"answer": "Hello!", "save_to_profile": false}'
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    answer, save = client.ask(history=[], question="Say hello")

    assert answer == "Hello!"
    assert save is False
    call_kwargs = mock_client.models.generate_content.call_args
    contents = call_kwargs.kwargs["contents"]
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
    mock_response.text = '{"answer": "Answer", "save_to_profile": false}'
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
    mock_response.text = '{"answer": "Answer", "save_to_profile": false}'
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
    mock_response.text = '{"answer": "Answer", "save_to_profile": false}'
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
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = '{"answer": "Sure!", "save_to_profile": false}'
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
    assert roles == ["user", "model", "user"]


@patch("bot.gemini.genai.Client")
def test_ask_save_to_profile_true(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = '{"answer": "Got it, noted!", "save_to_profile": true}'
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    answer, save = client.ask(history=[], question="Remember that I am a pilot")

    assert answer == "Got it, noted!"
    assert save is True


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


@patch("bot.gemini.genai.Client")
def test_extract_facts_returns_structured_list(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = (
        '[{"fact":"Alice prefers concise answers","importance":0.9,"confidence":0.95,'
        '"scope":"user"},{"fact":"This chat uses Ukrainian","importance":0.7,'
        '"confidence":0.9,"scope":"chat"}]'
    )
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    facts = client.extract_facts(
        existing_facts=["Alice likes short replies."],
        recent_history="[Alice]: Please keep it short and in Ukrainian",
        user_name="Alice",
    )
    assert facts[0]["fact"] == "Alice prefers concise answers"
    assert facts[0]["scope"] == "user"
    assert facts[1]["scope"] == "chat"


@patch("bot.gemini.genai.Client")
def test_extract_facts_falls_back_to_empty_list_on_invalid_json(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_response = MagicMock()
    mock_response.text = "No new facts."
    mock_client.models.generate_content.return_value = mock_response

    client = GeminiClient(api_key="fake-key")
    facts = client.extract_facts(
        existing_facts=[],
        recent_history="[Alice]: hello",
        user_name="Alice",
    )
    assert facts == []


def test_system_prompt_requires_optional_memory_usage():
    assert "ONLY when they are relevant" in SYSTEM_PROMPT
    assert "Do not force these facts" in SYSTEM_PROMPT
