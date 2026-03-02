"""Tests for bot.tools — tool factory functions."""

from unittest.mock import MagicMock

from bot.tools import create_memory_save, create_memory_search, create_web_search


# ── memory_search tool ────────────────────────────────────────────────


class TestMemorySearch:
    def test_memory_search_returns_results(self):
        """When search_memories returns results, the tool formats them and
        calls mark_used with the ids."""
        memory = MagicMock()
        embed_fn = MagicMock(return_value=[0.1, 0.2, 0.3])
        memory.search_memories.return_value = [
            {"id": 1, "content": "Alice works at Google", "importance": 0.8, "score": 0.9},
            {"id": 2, "content": "Bob likes hiking", "importance": 0.6, "score": 0.7},
        ]

        tool_fn = create_memory_search(memory, embed_fn)
        result = tool_fn.invoke({"query": "who works at Google"})

        embed_fn.assert_called_once_with("who works at Google")
        memory.search_memories.assert_called_once_with(
            query_embedding=[0.1, 0.2, 0.3], limit=5, cooldown_seconds=900
        )
        memory.mark_used.assert_called_once_with([1, 2])
        assert "Alice works at Google" in result
        assert "Bob likes hiking" in result

    def test_memory_search_returns_nothing_found(self):
        """When search_memories returns [], the tool returns a no-results message."""
        memory = MagicMock()
        embed_fn = MagicMock(return_value=[0.1, 0.2, 0.3])
        memory.search_memories.return_value = []

        tool_fn = create_memory_search(memory, embed_fn)
        result = tool_fn.invoke({"query": "unknown topic"})

        embed_fn.assert_called_once_with("unknown topic")
        memory.search_memories.assert_called_once()
        memory.mark_used.assert_not_called()
        assert result == "No memories found for this query."


# ── memory_save tool ──────────────────────────────────────────────────


class TestMemorySave:
    def test_memory_save_calls_save_or_update(self):
        """The save tool embeds the text and delegates to save_or_update."""
        memory = MagicMock()
        embed_fn = MagicMock(return_value=[0.4, 0.5, 0.6])
        memory.save_or_update.return_value = "inserted"

        tool_fn = create_memory_save(memory, embed_fn)
        result = tool_fn.invoke({"memory_text": "Alice works at Google since 2023"})

        embed_fn.assert_called_once_with("Alice works at Google since 2023")
        memory.save_or_update.assert_called_once_with(
            content="Alice works at Google since 2023",
            embedding=[0.4, 0.5, 0.6],
            importance=0.5,
        )
        assert result == "inserted"

    def test_memory_save_with_custom_importance(self):
        """When importance is provided, it passes through to save_or_update."""
        memory = MagicMock()
        embed_fn = MagicMock(return_value=[0.1, 0.2])
        memory.save_or_update.return_value = "updated"

        tool_fn = create_memory_save(memory, embed_fn)
        result = tool_fn.invoke({"memory_text": "Important fact", "importance": 0.9})

        memory.save_or_update.assert_called_once_with(
            content="Important fact",
            embedding=[0.1, 0.2],
            importance=0.9,
        )
        assert result == "updated"


# ── web_search tool ───────────────────────────────────────────────────


class TestWebSearch:
    def test_web_search_returns_content(self):
        """The web_search tool binds google_search and returns content."""
        llm = MagicMock()
        bound_llm = MagicMock()
        llm.bind_tools.return_value = bound_llm

        response = MagicMock()
        response.content = "The weather in Kyiv is 15C and sunny."
        bound_llm.invoke.return_value = response

        tool_fn = create_web_search(llm)
        result = tool_fn.invoke({"query": "weather in Kyiv"})

        llm.bind_tools.assert_called_once_with([{"google_search": {}}])
        assert "15C" in result
        assert "sunny" in result

    def test_web_search_returns_fallback_when_empty(self):
        """When LLM returns empty content, the tool returns a fallback message."""
        llm = MagicMock()
        bound_llm = MagicMock()
        llm.bind_tools.return_value = bound_llm

        response = MagicMock()
        response.content = ""
        bound_llm.invoke.return_value = response

        tool_fn = create_web_search(llm)
        result = tool_fn.invoke({"query": "something obscure"})

        assert result == "No results found."
