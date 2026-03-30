import litellm
from typing import Any


class EmbeddingService:
    def __init__(self, settings, pool) -> None:
        self._settings = settings
        self._pool = pool

    async def embed(self, text: str) -> list[float]:
        """Embed text via LiteLLM using the configured embedding model."""
        model = await self._settings.get("embedding_model")
        response = await litellm.aembedding(model=model, input=[text])
        return response.data[0].embedding

    async def save(self, node_id: int, text: str) -> None:
        """Embed text and store in node_embeddings table."""
        vector = await self.embed(text)
        vector_str = "[" + ",".join(str(round(v, 6)) for v in vector) + "]"
        await self._pool.execute(
            """
            INSERT INTO node_embeddings (node_id, embedding, updated_at)
            VALUES ($1, $2::vector, now())
            ON CONFLICT (node_id) DO UPDATE
              SET embedding = EXCLUDED.embedding, updated_at = now()
            """,
            node_id,
            vector_str,
        )

    async def search(self, query_vector: list[float], limit: int = 5) -> list[int]:
        """Return node_ids sorted by cosine similarity to query_vector."""
        vector_str = "[" + ",".join(str(round(v, 6)) for v in query_vector) + "]"
        rows = await self._pool.fetch(
            """
            SELECT node_id
            FROM node_embeddings
            ORDER BY embedding <=> $1::vector
            LIMIT $2
            """,
            vector_str,
            limit,
        )
        return [r["node_id"] for r in rows]

    async def search_text(self, query: str, limit: int = 5) -> list[int]:
        """Embed query text and return nearest node_ids."""
        vector = await self.embed(query)
        return await self.search(vector, limit=limit)
