"""Intent classifier sub-agent — pure heuristics, no LLM."""
from __future__ import annotations
import re
from .base import BaseSubAgent, SubAgentResult

_QUESTION_RE = re.compile(
    r"(\?|як|чому|коли|де|хто|що|навіщо|скільки|чи |who|what|when|where|why|how|is |are |can |do |does )",
    re.IGNORECASE,
)
_REQUEST_RE = re.compile(
    r"(допоможи|зроби|напиши|поясни|розкажи|знайди|порахуй|перекладіть|help|write|explain|find|calculate|translate"
    r"|помоги|сделай|объясни|найди|напиши)",
    re.IGNORECASE,
)
_TECHNICAL_RE = re.compile(
    r"(функція|алгоритм|порахуй|обчисли|поясни|перекладіть"
    r"|код|code|function|algorithm|calculate|explain|translate"
    r"|функция|алгоритм|посчитай|объясни|переведи)",
    re.IGNORECASE,
)
_WEB_RE = re.compile(
    r"(погода|ціна|новини|сьогодні|зараз|курс"
    r"|weather|price|news|today|now|rate"
    r"|погода|цена|новости|сегодня|сейчас|курс)",
    re.IGNORECASE,
)


def _classify_complexity(
    text: str,
    intent: str,
    *,
    has_photo: bool,
    has_url: bool,
    has_forward: bool,
) -> str:
    if has_photo or has_url or has_forward:
        return "complex"
    if intent == "request":
        return "complex"
    if len(text) > 150:
        return "complex"
    if _TECHNICAL_RE.search(text):
        return "complex"
    if _WEB_RE.search(text):
        return "complex"
    return "simple"


class IntentClassifier(BaseSubAgent):
    name = "intent_classifier"

    async def run(
        self,
        *,
        text: str,
        has_photo: bool = False,
        has_url: bool = False,
        has_forward: bool = False,
        **kwargs,
    ) -> SubAgentResult:
        if _REQUEST_RE.search(text):
            intent = "request"
        elif _QUESTION_RE.search(text):
            intent = "question"
        else:
            intent = "other"

        complexity = _classify_complexity(
            text, intent,
            has_photo=has_photo,
            has_url=has_url,
            has_forward=has_forward,
        )
        return SubAgentResult(
            agent_name=self.name,
            content=intent,
            metadata={"intent": intent, "complexity": complexity},
        )
