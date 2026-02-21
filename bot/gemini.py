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
    "USE OF MEMORY: Use the provided user profiles and knowledge base ONLY when they are relevant to the current conversation. Do not force these facts into your response if they don't fit naturally.\n\n"
    "RESPONSE FORMAT: Always reply with a valid JSON object on a single line with exactly three keys:\n"
    "  {\"answer\": \"<your reply here>\", \"save_to_profile\": <true|false>, \"save_to_memory\": <true|false>}\n"
    "Set save_to_profile to true when:\n"
    "1. The user explicitly asks you to remember or save information.\n"
    "2. The user shares a significant, enduring personal fact, unique characteristic, or stable preference that would be valuable for your long-term memory of them.\n"
    "Set save_to_memory to true when:\n"
    "1. The user explicitly asks to remember information for the whole chat/group.\n"
    "2. The conversation contains significant, enduring group-level facts (shared norms, recurring topics, stable context) that should be stored in chat memory.\n"
    "For any normal question or situational conversation set both flags to false. "
    "Do NOT wrap the JSON in markdown code fences. Output raw JSON only."
)


class GeminiClient:
    def __init__(self, api_key: str):
        self._client = genai.Client(api_key=api_key)
        self._model = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
        self._embedding_model = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")

    def ask(
        self,
        history: list[dict],
        question: str,
        user_profile: str = "",
        chat_profile: str = "",
        chat_members: list[str] | None = None,
        retrieved_profiles: list[str] | None = None,
    ) -> tuple[str, bool, bool]:
        """Send a question to Gemini with full multi-turn conversation history.

        Returns:
            A tuple of (answer_text, save_to_profile, save_to_memory).

        Args:
            history: List of ``{"role": "user"|"model", "text": str}`` dicts
                     from ``SessionManager.get_history()``. Does NOT include
                     the current ``question`` — that is appended automatically.
            question: The current user message (already stripped of bot mention).
            user_profile: Optional profile text injected as context.
            chat_profile: Optional chat-level memory injected as context.
            chat_members: Optional list of known chat member names.
            retrieved_profiles: Optional list of profile strings retrieved via vector search.
        """
        context_parts = []
        if user_profile:
            context_parts.append(f"Profile of the person asking:\n{user_profile}")
        if chat_profile:
            context_parts.append(f"Profile of this chat/group:\n{chat_profile}")
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
            author = entry.get("author") or ("bot" if entry["role"] == "model" else "user")
            text = f"[{author}]: {entry['text']}"
            
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
            f"You are updating the persistent memory profile for user '{user_name}'.\n\n"
            f"Current profile:\n{existing_profile or '(empty)'}\n\n"
            f"Recent conversation:\n{recent_history}\n\n"
            f"INSTRUCTIONS:\n"
            f"1. Extract ONLY hard, enduring facts or unique characteristics about {user_name} (e.g., profession, location, stable preferences, significant hobbies, life details).\n"
            f"2. STRICTLY IGNORE situational banter, small talk, temporary plans, or topics of current conversation (e.g., discussing today's weather, a specific news event, or a temporary problem).\n"
            f"3. Do not assume or speculate. Only record facts explicitly stated or strongly implied by {user_name}.\n"
            f"4. If no NEW enduring facts are found in the recent conversation, you MUST return the exact Current Profile unchanged without adding any new text.\n"
            f"5. Write in the third person (e.g., '{user_name} is...'). Keep it concise (max 150 words).\n"
        )
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are a strict memory assistant. Your ONLY job is to extract permanent, long-lasting facts about a user "
                    "from chat messages. Never record situational chatter, moods, or temporary events. Be objective and factual."
                ),
            ),
        )
        text = response.text
        if text is None:
            return existing_profile
        return text.strip()

    def extract_chat_profile(
        self, existing_profile: str, recent_history: str, chat_name: str
    ) -> str:
        prompt = (
            f"You are updating the persistent memory profile for chat '{chat_name}'.\n\n"
            f"Current chat profile:\n{existing_profile or '(empty)'}\n\n"
            f"Recent conversation:\n{recent_history}\n\n"
            f"INSTRUCTIONS:\n"
            f"1. Extract ONLY durable group-level facts: recurring topics, shared norms/rules, stable interests, and long-term context that helps in future conversations.\n"
            f"2. STRICTLY IGNORE temporary chatter, one-off events, short-lived plans, and day-specific details.\n"
            f"3. Do not assume or speculate. Keep only facts explicitly present in the conversation.\n"
            f"4. If there are no NEW durable chat-level facts, return the Current chat profile unchanged.\n"
            f"5. Write concise neutral prose, max 180 words.\n"
        )
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are a strict memory assistant for Telegram chats. "
                    "Store only long-lasting group context useful for future replies."
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
            model=self._embedding_model,
            contents=[text],
        )
        return response.embeddings[0].values


def _parse_bot_response(raw: str) -> tuple[str, bool, bool]:
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
        save_profile = bool(data.get("save_to_profile", False))
        save_memory = bool(data.get("save_to_memory", False))
        return answer, save_profile, save_memory
    except (json.JSONDecodeError, AttributeError):
        # Model didn't return valid JSON — treat the whole text as the answer.
        return raw, False, False
