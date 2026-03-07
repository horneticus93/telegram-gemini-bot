"""Intent classifier sub-agent — pure heuristics, no LLM."""
from __future__ import annotations
import re
from .base import BaseSubAgent, SubAgentResult

_QUESTION_RE = re.compile(
    r"(\?|як|чому|коли|де|хто|що|навіщо|скільки|чи |who|what|when|where|why|how|is |are |can |do |does )",
    re.IGNORECASE,
)
_REQUEST_RE = re.compile(
    r"(допоможи|зроби|напиши|поясни|розкажи|знайди|порахуй|перекладіть|help|write|explain|find|calculate|translate)",
    re.IGNORECASE,
)


class IntentClassifier(BaseSubAgent):
    name = "intent_classifier"

    async def run(self, *, text: str, **kwargs) -> SubAgentResult:
        if _REQUEST_RE.search(text):
            intent = "request"
        elif _QUESTION_RE.search(text):
            intent = "question"
        else:
            intent = "other"
        return SubAgentResult(agent_name=self.name, content=intent)
