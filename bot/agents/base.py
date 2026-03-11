"""Base classes for sub-agents in the multi-agent pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SubAgentResult:
    """Result returned by any sub-agent."""
    agent_name: str
    content: str
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseSubAgent:
    """Abstract base for all sub-agents.

    Subclasses must implement ``run()``.
    """
    name: str = "base"

    async def run(self, **kwargs) -> SubAgentResult:
        raise NotImplementedError
