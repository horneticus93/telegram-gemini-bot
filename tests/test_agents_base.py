import pytest
from unittest.mock import AsyncMock, MagicMock
from bot.agents.base import BaseSubAgent, SubAgentResult


def test_sub_agent_result_fields():
    result = SubAgentResult(agent_name="test", content="hello", confidence=0.9)
    assert result.agent_name == "test"
    assert result.content == "hello"
    assert result.confidence == 0.9


def test_sub_agent_result_defaults():
    result = SubAgentResult(agent_name="test", content="hello")
    assert result.confidence == 1.0
    assert result.metadata == {}
