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
        self._model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    def ask(
        self,
        history: str,
        question: str,
        user_profile: str = "",
        chat_members: list[str] | None = None,
    ) -> str:
        context_parts = []
        if user_profile:
            context_parts.append(f"Profile of the person asking:\n{user_profile}")
        if chat_members:
            context_parts.append(
                f"Known members in this chat: {', '.join(chat_members)}"
            )
        context_block = ("\n\n" + "\n\n".join(context_parts)) if context_parts else ""

        if history:
            contents = (
                f"Here is the recent group conversation:\n\n{history}"
                f"{context_block}"
                f"\n\nNow answer this: {question}"
            )
        else:
            contents = (
                f"{context_block.strip()}\n\n{question}".strip()
                if context_block
                else question
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
