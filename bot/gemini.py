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
    "USE OF MEMORY: Use the provided user profiles and knowledge base ONLY when they are relevant to the current conversation. Do not force these facts into your response if they don't fit naturally. "
    "If memory is not clearly useful, ignore it. Never repeat the same remembered fact in consecutive replies unless the user asks for it.\n\n"
    "RESPONSE FORMAT: Always reply with a valid JSON object on a single line with exactly two keys:\n"
    "  {\"answer\": \"<your reply here>\", \"save_to_profile\": <true|false>}\n"
    "Set save_to_profile to true when:\n"
    "1. The user explicitly asks you to remember or save information.\n"
    "2. The user shares a significant, enduring personal fact, unique characteristic, or stable preference that would be valuable for your long-term memory of them.\n"
    "For any normal question or situational conversation set save_to_profile to false. "
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
        chat_members: list[str] | None = None,
        retrieved_profiles: list[str] | None = None,
    ) -> tuple[str, bool]:
        """Send a question to Gemini with full multi-turn conversation history.

        Returns:
            A tuple of (answer_text, save_to_profile).

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

    def extract_facts(
        self,
        existing_facts: list[str],
        recent_history: str,
        user_name: str,
    ) -> list[dict]:
        facts_block = "\n".join(f"- {fact}" for fact in existing_facts) or "(none)"
        prompt = (
            f"You are extracting persistent memory facts for user '{user_name}'.\n\n"
            f"Existing facts:\n{facts_block}\n\n"
            f"Recent conversation:\n{recent_history}\n\n"
            "Return ONLY a JSON array of objects. Each object must be:\n"
            '{"fact":"...", "importance":0.0-1.0, "confidence":0.0-1.0, "scope":"user"|"chat"}\n\n'
            "Rules:\n"
            "1. Include only stable or reusable facts (preferences, enduring traits, recurring constraints, long-term chat conventions).\n"
            "2. Skip temporary details, emotions of the moment, and one-off tasks.\n"
            "3. Keep each fact short and atomic.\n"
            "4. Emit an empty array [] when there are no good new facts.\n"
            "5. Do not output markdown, prose, or explanations."
        )
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are a strict memory extraction system. "
                    "Output valid JSON only."
                ),
            ),
        )
        text = (response.text or "").strip()
        if not text:
            return []
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            data = json.loads(text)
            if not isinstance(data, list):
                return []
            valid_facts: list[dict] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                fact_text = str(item.get("fact", "")).strip()
                if not fact_text:
                    continue
                scope = item.get("scope", "user")
                if scope not in {"user", "chat"}:
                    scope = "user"
                valid_facts.append(
                    {
                        "fact": fact_text,
                        "importance": float(item.get("importance", 0.5)),
                        "confidence": float(item.get("confidence", 0.8)),
                        "scope": scope,
                    }
                )
            return valid_facts
        except (json.JSONDecodeError, TypeError, ValueError):
            return []

    def decide_fact_action(
        self,
        candidate_fact: str,
        scope: str,
        similar_facts: list[dict],
        user_name: str,
    ) -> dict:
        if scope not in {"user", "chat"} or not candidate_fact.strip() or not similar_facts:
            return {"action": "keep_add_new", "target_fact_id": None}

        facts_block = "\n".join(
            (
                f"- id={item.get('fact_id')} "
                f"score={float(item.get('similarity', 0.0)):.3f} "
                f"text={item.get('fact_text', '')}"
            )
            for item in similar_facts
        )
        prompt = (
            f"You are deciding how to store a memory fact for user '{user_name}'.\n\n"
            f"New candidate fact (scope={scope}): {candidate_fact}\n\n"
            f"Most similar existing facts:\n{facts_block}\n\n"
            "Return ONLY one JSON object with exactly this shape:\n"
            '{"action":"keep_add_new|update_existing|deactivate_existing|noop","target_fact_id":<number|null>}\n\n'
            "Rules:\n"
            "1. Use update_existing when the candidate corrects or refines the same underlying attribute as an existing fact.\n"
            "2. Use deactivate_existing when an existing fact became invalid and the candidate should not replace it.\n"
            "3. Use keep_add_new when candidate is a distinct stable fact.\n"
            "4. Use noop when candidate should not be stored in long-term memory.\n"
            "5. For update_existing/deactivate_existing, target_fact_id must be one of the listed ids.\n"
            "6. No explanations, no markdown."
        )
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are a strict memory conflict resolver. "
                    "Output valid JSON only."
                ),
            ),
        )
        text = (response.text or "").strip()
        if not text:
            return {"action": "keep_add_new", "target_fact_id": None}
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                return {"action": "keep_add_new", "target_fact_id": None}
            action = str(data.get("action", "keep_add_new")).strip().lower()
            if action not in {
                "keep_add_new",
                "update_existing",
                "deactivate_existing",
                "noop",
            }:
                action = "keep_add_new"
            target_fact_id = data.get("target_fact_id")
            try:
                target_fact_id = int(target_fact_id) if target_fact_id is not None else None
            except (TypeError, ValueError):
                target_fact_id = None
            valid_ids = {
                int(item["fact_id"])
                for item in similar_facts
                if item.get("fact_id") is not None
            }
            if action in {"update_existing", "deactivate_existing"} and target_fact_id not in valid_ids:
                return {"action": "keep_add_new", "target_fact_id": None}
            if action in {"keep_add_new", "noop"}:
                target_fact_id = None
            return {"action": action, "target_fact_id": target_fact_id}
        except (json.JSONDecodeError, TypeError, ValueError, KeyError):
            return {"action": "keep_add_new", "target_fact_id": None}

    def embed_text(self, text: str) -> list[float]:
        """Generate an embedding vector for the given text."""
        if not text:
            return []

        response = self._client.models.embed_content(
            model=self._embedding_model,
            contents=[text],
        )
        return response.embeddings[0].values

    def extract_date_from_fact(self, fact_text: str) -> dict | None:
        """Analyze a fact for recurring date events (birthday, anniversary, etc.).

        Returns a dict with event_type, event_date (MM-DD), and title if a
        recurring date is found, or None otherwise.
        """
        prompt = (
            "Analyze this fact and determine if it contains a recurring date event "
            "(birthday, anniversary, or other annual event).\n\n"
            f"Fact: {fact_text}\n\n"
            "If YES, return a JSON object:\n"
            '{"event_type":"birthday"|"anniversary"|"custom", "event_date":"MM-DD", "title":"short description"}\n\n'
            "If NO date event found, return exactly: null\n\n"
            "Rules:\n"
            "1. event_date must be MM-DD format (e.g. 03-10 for March 10).\n"
            "2. title should be a brief human-readable label.\n"
            "3. No markdown, no explanations."
        )
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are a strict date extraction system. "
                    "Output valid JSON or null only."
                ),
            ),
        )
        text = (response.text or "").strip()
        if not text:
            return None
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                return None
            event_type = str(data.get("event_type", "custom")).strip().lower()
            if event_type not in {"birthday", "anniversary", "custom"}:
                event_type = "custom"
            return {
                "event_type": event_type,
                "event_date": str(data.get("event_date", "")),
                "title": str(data.get("title", "")),
            }
        except (json.JSONDecodeError, TypeError, ValueError):
            return None


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
        save_profile = bool(data.get("save_to_profile", False))
        return answer, save_profile
    except (json.JSONDecodeError, AttributeError):
        # Model didn't return valid JSON — treat the whole text as the answer.
        return raw, False
