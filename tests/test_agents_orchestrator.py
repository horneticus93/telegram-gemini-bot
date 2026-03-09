import pytest
from unittest.mock import AsyncMock, MagicMock
from bot.agents.orchestrator import AgentOrchestrator
from bot.agents.base import SubAgentResult


@pytest.fixture
def mock_agents():
    mention = AsyncMock()
    mention.run.return_value = SubAgentResult(
        agent_name="mention_detector",
        content="addressed",
        metadata={"is_addressed": True, "new_alias": None},
    )
    memory = AsyncMock()
    memory.run.return_value = SubAgentResult(
        agent_name="memory_retriever", content="- Іван любить каву"
    )
    context = AsyncMock()
    context.run.return_value = SubAgentResult(
        agent_name="context_analyst", content="Позитивний тон", metadata={"tone": "positive"}
    )
    return mention, memory, context


def _make_intent_mock():
    intent = AsyncMock()
    intent.run.return_value = SubAgentResult(
        agent_name="intent_classifier",
        content="question",
        metadata={"intent": "question", "complexity": "complex"},
    )
    return intent


def _make_relevance_mock(pass_through=True):
    """Returns a RelevanceJudge mock that passes all results through by default."""
    judge = AsyncMock()
    judge.run.side_effect = lambda *, text, sub_agent_results, **kwargs: sub_agent_results
    return judge


@pytest.mark.asyncio
async def test_orchestrator_runs_always_on_agents(mock_agents):
    mention, memory, context = mock_agents
    orch = AgentOrchestrator(
        mention_detector=mention,
        memory_retriever=memory,
        context_analyst=context,
        image_analyzer=None,
        link_extractor=None,
        repost_analyzer=None,
        intent_classifier=_make_intent_mock(),
        relevance_judge=_make_relevance_mock(),
        memory=MagicMock(),
    )
    brief = await orch.build_pre_context(
        text="привіт",
        chat_id=1,
        recent_messages=[],
        has_photo=False,
        has_forward=False,
    )
    mention.run.assert_called_once()
    memory.run.assert_called_once()
    context.run.assert_called_once()
    pre_context, complexity = brief
    assert isinstance(pre_context, str)
    assert complexity in ("simple", "complex")


@pytest.mark.asyncio
async def test_orchestrator_skips_image_when_no_photo(mock_agents):
    mention, memory, context = mock_agents
    image_agent = AsyncMock()
    orch = AgentOrchestrator(
        mention_detector=mention,
        memory_retriever=memory,
        context_analyst=context,
        image_analyzer=image_agent,
        link_extractor=None,
        repost_analyzer=None,
        intent_classifier=_make_intent_mock(),
        relevance_judge=_make_relevance_mock(),
        memory=MagicMock(),
    )
    await orch.build_pre_context(
        text="текст без фото",
        chat_id=1,
        recent_messages=[],
        has_photo=False,
        has_forward=False,
    )
    image_agent.run.assert_not_called()


@pytest.mark.asyncio
async def test_build_pre_context_returns_tuple(mock_agents):
    """build_pre_context must return (str, str) tuple."""
    mention, memory, context = mock_agents
    orch = AgentOrchestrator(
        mention_detector=mention,
        memory_retriever=memory,
        context_analyst=context,
        image_analyzer=None,
        link_extractor=None,
        repost_analyzer=None,
        intent_classifier=_make_intent_mock(),
        relevance_judge=_make_relevance_mock(),
        memory=MagicMock(),
    )
    result = await orch.build_pre_context(
        text="привіт",
        chat_id=1,
        recent_messages=[],
        has_photo=False,
        has_forward=False,
    )
    assert isinstance(result, tuple)
    assert len(result) == 2
    pre_context, complexity = result
    assert isinstance(pre_context, str)
    assert complexity in ("simple", "complex")


@pytest.mark.asyncio
async def test_build_pre_context_passes_flags_to_intent_classifier(mock_agents):
    """has_photo/has_url/has_forward are forwarded to IntentClassifier.run()."""
    mention, memory, context = mock_agents
    intent_mock = AsyncMock()
    intent_mock.run.return_value = SubAgentResult(
        agent_name="intent_classifier",
        content="other",
        metadata={"intent": "other", "complexity": "complex"},
    )
    orch = AgentOrchestrator(
        mention_detector=mention,
        memory_retriever=memory,
        context_analyst=context,
        image_analyzer=None,
        link_extractor=None,
        repost_analyzer=None,
        intent_classifier=intent_mock,
        relevance_judge=_make_relevance_mock(),
        memory=MagicMock(),
    )
    await orch.build_pre_context(
        text="глянь",
        chat_id=1,
        recent_messages=[],
        has_photo=True,
        has_forward=False,
    )
    call_kwargs = intent_mock.run.call_args[1]
    assert call_kwargs.get("has_photo") is True


@pytest.mark.asyncio
async def test_build_pre_context_complexity_from_intent_metadata(mock_agents):
    """complexity in returned tuple comes from intent_classifier metadata."""
    mention, memory, context = mock_agents
    intent_mock = AsyncMock()
    intent_mock.run.return_value = SubAgentResult(
        agent_name="intent_classifier",
        content="other",
        metadata={"intent": "other", "complexity": "simple"},
    )
    orch = AgentOrchestrator(
        mention_detector=mention,
        memory_retriever=memory,
        context_analyst=context,
        image_analyzer=None,
        link_extractor=None,
        repost_analyzer=None,
        intent_classifier=intent_mock,
        relevance_judge=_make_relevance_mock(),
        memory=MagicMock(),
    )
    _, complexity = await orch.build_pre_context(
        text="ок",
        chat_id=1,
        recent_messages=[],
        has_photo=False,
        has_forward=False,
    )
    assert complexity == "simple"
