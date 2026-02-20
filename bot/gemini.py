import json
import os
from google import genai
from google.genai import types

SYSTEM_PROMPT = (
    "You are a helpful assistant in a Telegram group chat. "
    "Keep your responses short and conversational — maximum 3 to 5 sentences. "
    "Write like a person texting, not like a document. "
    "If you need to search the web for current information, do so and include the answer in this same response. "
    "IMPORTANT: Never say you will look something up and get back later. "
    "Never defer your answer to a future message. "
    "Always provide your complete answer right now, in this single response.\n\n"
    "RESPONSE FORMAT: Always reply with a valid JSON object on a single line with exactly two keys:\n"
    "  {\"answer\": \"<your reply here>\", \"save_to_profile\": <true|false>}\n"
    "Set save_to_profile to true ONLY when the user is explicitly asking you to remember, "
    "save, or keep some personal information about themselves "
    "(e.g. 'remember that I am a developer', 'save that I prefer dark mode'). "
    "For any normal question or conversation set save_to_profile to false. "
    "Do NOT wrap the JSON in markdown code fences. Output raw JSON only."
)


class GeminiClient:
    def __init__(self, api_key: str):
        self._client = genai.Client(api_key=api_key)
        self._model = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")

    def ask(
        self,
        history: list[dict],
        question: str,
        user_profile: str = "",
        chat_members: list[str] | None = None,
        retrieved_profiles: list[str] | None = None,
    ) -> tuple[str, bool]:
        """Send a question to Gemini with full multi-turn conversation history.

        Returns:
            A tuple of (answer_text, save_to_profile) where save_to_profile is
            True when the user asked to save some personal information.

        Args:
            history: List of ``{"role": "user"|"model", "text": str}`` dicts
                     from ``SessionManager.get_history()``. Does NOT include
                     the current ``question`` — that is appended automatically.
            question: The current user message (already stripped of bot mention).
            user_profile: Optional profile text injected as context.
            chat_members: Optional list of known chat member names.
            retrieved_profiles: Optional list of profile strings retrieved via vector search.
        """
        context_parts = []
        if user_profile:
            context_parts.append(f"Profile of the person asking:\n{user_profile}")
        if chat_members:
            context_parts.append(
                f"Known members in this chat: {', '.join(chat_members)}"
            )
        if retrieved_profiles:
            profiles_text = "\n".join(f"- {p}" for p in retrieved_profiles)
            context_parts.append(
                f"Knowledge base (facts about chat members):\n{profiles_text}"
            )
        context_prefix = "\n\n".join(context_parts)

        # Build the structured contents list from history turns.
        contents: list[types.Content] = []
        for i, entry in enumerate(history):
            text = entry["text"]
            # Prepend context to the very first user turn so the model sees it
            # before any history, without creating an extra artificial turn.
            if i == 0 and context_prefix and entry["role"] == "user":
                text = f"{context_prefix}\n\n{text}"
            contents.append(
                types.Content(
                    role=entry["role"],
                    parts=[types.Part(text=text)],
                )
            )

        # If context exists but history is empty (or starts with a model turn),
        # inject it as a leading user message so it still reaches the model.
        if context_prefix and (not contents or contents[0].role != "user"):
            contents.insert(
                0,
                types.Content(
                    role="user",
                    parts=[types.Part(text=context_prefix)],
                ),
            )

        # Append the current question as the final user turn.
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part(text=question)],
            )
        )

        response = self._client.models.generate_content(
            model=self._model,
            contents=contents,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                system_instruction=SYSTEM_PROMPT,
            ),
        )
        raw = response.text
        if raw is None:
            raise ValueError("Gemini returned no text response")
        return _parse_bot_response(raw)

    def extract_profile(
        self, existing_profile: str, recent_history: str, user_name: str
    ) -> str:
        prompt = (
            f"Update the memory profile for {user_name} based on their recent messages.\n\n"
            f"Current profile:\n{existing_profile or '(empty)'}\n\n"
            f"Recent conversation (focus on messages from {user_name}):\n{recent_history}\n\n"
            f"Write an updated profile in third person (e.g. '{user_name} is...'). "
            f"Include: interests, job, preferences, facts they shared, communication style. "
            f"Max 150 words. If nothing new, return the current profile unchanged."
        )
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are a memory assistant. Extract personal facts about a specific user "
                    "from chat messages and maintain their concise profile. Be factual, no speculation."
                ),
            ),
        )
        text = response.text
        if text is None:
            return existing_profile
        return text.strip()

    def embed_text(self, text: str) -> list[float]:
        """Generate an embedding vector for the given text."""
        if not text:
            return []
        
        response = self._client.models.embed_content(
            model="text-embedding-004",
            contents=text,
        )
        return response.embeddings[0].values


def _parse_bot_response(raw: str) -> tuple[str, bool]:
    """Parse the JSON response from the bot.

    Falls back gracefully if the model didn't honour the JSON format.
    """
    text = raw.strip()
    # Strip markdown code fences if the model added them anyway.
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
        answer = str(data.get("answer", raw))
        save = bool(data.get("save_to_profile", False))
        return answer, save
    except (json.JSONDecodeError, AttributeError):
        # Model didn't return valid JSON — treat the whole text as the answer.
        return raw, False
