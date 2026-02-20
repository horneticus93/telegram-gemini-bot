from google import genai
from google.genai import types

SYSTEM_PROMPT = (
    "You are a helpful assistant in a Telegram group chat. "
    "Keep your responses short and conversational — maximum 3 to 5 sentences. "
    "Write like a person texting, not like a document. "
    "If you need to search the web for current information, do so, "
    "but still summarize briefly."
)


class GeminiClient:
    def __init__(self, api_key: str):
        self._client = genai.Client(api_key=api_key)
        self._model = "gemini-2.0-flash"

    def ask(self, history: str, question: str) -> str:
        if history:
            contents = (
                f"Here is the recent group conversation:\n\n{history}"
                f"\n\nNow answer this: {question}"
            )
        else:
            contents = question

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
