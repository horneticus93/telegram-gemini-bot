"""Prompts for sub-agents."""

MENTION_DETECTOR_PROMPT = """\
You are analyzing a Telegram message to determine if the bot is being addressed.

Bot aliases in this chat: {aliases}

Message: "{text}"

Respond ONLY with valid JSON (no markdown, no explanation):
{{"is_addressed": <true|false>, "confidence": <0.0-1.0>, "new_alias": <"name"|null>}}

- is_addressed: true if the message is directed at the bot (by alias, context, or implicit reference)
- confidence: how confident you are (0.0 = not sure, 1.0 = certain)
- new_alias: if a new name for the bot is used that is NOT in the aliases list, return it; otherwise null
"""

MEMORY_RETRIEVER_PROMPT = """\
You are a memory retrieval assistant. Given the conversation context below, \
identify the most important search queries to find relevant bot memories.

Recent message: "{text}"
Context: "{context}"

Return up to 3 search queries as a JSON array of strings. Example:
["query one", "query two"]
Respond ONLY with valid JSON.
"""

CONTEXT_ANALYST_PROMPT = """\
Analyze the last {n} messages of this Telegram chat and return a brief analysis.

Messages:
{messages}

Respond ONLY with valid JSON:
{{"tone": "<neutral|positive|negative|tense|playful>", "main_topics": ["topic1"], "active_participants": ["name1"], "summary": "<1 sentence>"}}
"""

LINK_EXTRACTOR_PROMPT = """\
Visit and summarize the key information from this URL for a Telegram chat assistant.
URL: {url}

Return a 2-3 sentence summary of the most important content. Be concise.
"""

IMAGE_ANALYZER_PROMPT = """\
Describe this image briefly for a Telegram chat assistant. \
Focus on: what is shown, any text visible, and any relevant context.
Keep it under 3 sentences.
"""

REPOST_ANALYZER_PROMPT = """\
This is a forwarded Telegram message. Analyze its content and provide:
1. A brief summary (1-2 sentences)
2. The apparent original source/author if identifiable

Forwarded content: "{content}"

Respond ONLY with valid JSON:
{{"summary": "<text>", "source": "<text or null>"}}
"""

MEMORY_WATCHER_PROMPT = """\
You are analyzing a conversation to identify facts worth saving to long-term memory.

Recent exchange:
{messages}

Identify up to 3 important facts (personal info, preferences, events, decisions).
For each fact include full context: who + what + where.

Respond ONLY with valid JSON array:
[{{"fact": "<text>", "importance": <0.0-1.0>}}]

If nothing worth saving, return: []
"""

RELEVANCE_JUDGE_PROMPT = """\
You are a relevance filter. Given the user's message and a set of sub-agent results, \
determine which results are actually useful for answering the user.

User message: "{text}"

Sub-agent results:
{results}

Return ONLY the names of relevant agents as a JSON array. Example: ["memory_retriever", "context_analyst"]
If all are relevant, include all. If none, return [].
"""
