import json
import litellm
from dataclasses import dataclass
from bot.tools import TOOL_DEFINITIONS, execute_tool

MAX_TOOL_STEPS = 6


@dataclass
class LLMResult:
    text: str
    tokens_used: int
    model_used: str


class LLMService:
    def __init__(self, settings, graph, embeddings) -> None:
        self._settings = settings
        self._graph = graph
        self._embeddings = embeddings

    async def complete(self, messages: list[dict], has_image: bool) -> LLMResult:
        if has_image:
            model = await self._settings.get("vision_model")
        else:
            model = await self._settings.get("chat_model")

        tavily_key = await self._settings.get("tavily_api_key", default=None)

        total_tokens = 0
        final_model = model
        steps = 0

        while steps < MAX_TOOL_STEPS:
            steps += 1
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
            )
            choice = response.choices[0]
            total_tokens += response.usage.total_tokens if response.usage else 0
            final_model = response.model or model

            tool_calls = choice.message.tool_calls or []
            if not tool_calls:
                # No more tool calls — final answer
                text = choice.message.content or ""
                return LLMResult(text=text, tokens_used=total_tokens, model_used=final_model)

            # Append assistant message with tool calls
            messages.append({
                "role": "assistant",
                "content": choice.message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            })

            # Execute each tool and append results
            for tc in tool_calls:
                args = json.loads(tc.function.arguments)
                tool_result = await execute_tool(
                    tc.function.name,
                    args,
                    graph=self._graph,
                    embeddings=self._embeddings,
                    tavily_key=tavily_key,
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result,
                })

        # Fallback if max steps reached
        return LLMResult(text="(max tool steps reached)", tokens_used=total_tokens, model_used=final_model)
