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
    "Always provide your complete answer right now, in this single response."
)


class GeminiClient:
    def __init__(self, api_key: str):
        self._client = genai.Client(api_key=api_key)
        self._model = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
        self._classifier_model = os.getenv("GEMINI_CLASSIFIER_MODEL", "gemini-2.5-flash-lite")

    def ask(
        self,
        history: list[dict],
        question: str,
        user_profile: str = "",
        chat_members: list[str] | None = None,
    ) -> str:
        """Send a question to Gemini with full multi-turn conversation history.

        Args:
            history: List of ``{"role": "user"|"model", "text": str}`` dicts
                     from ``SessionManager.get_history()``. Does NOT include
                     the current ``question`` — that is appended automatically.
            question: The current user message (already stripped of bot mention).
            user_profile: Optional profile text injected as context.
            chat_members: Optional list of known chat member names.
        """
        context_parts = []
        if user_profile:
            context_parts.append(f"Profile of the person asking:\n{user_profile}")
        if chat_members:
            context_parts.append(
                f"Known members in this chat: {', '.join(chat_members)}"
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
        text = response.text
        if text is None:
            raise ValueError("Gemini returned no text response")
        return text


    def detect_remember_intent(self, message: str) -> bool:
        """Return True if the user is asking to save / remember some information."""
        prompt = (
            "Does the following message express a request to save, remember, or store "
            "some piece of information about the user? "
            "Answer with a single word: YES or NO.\n\n"
            f"Message: {message}"
        )
        response = self._client.models.generate_content(
            model=self._classifier_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are an intent classifier. "
                    "Reply only with YES or NO, nothing else."
                ),
            ),
        )
        text = (response.text or "").strip().upper()
        return text.startswith("YES")

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
