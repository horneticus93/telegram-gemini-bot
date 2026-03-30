import pytest
from unittest.mock import AsyncMock, patch
from memory.embeddings import EmbeddingService


@pytest.fixture
def mock_settings():
    s = AsyncMock()
    s.get = AsyncMock(return_value="gemini/gemini-embedding-001")
    return s


@pytest.mark.asyncio
async def test_embed_returns_vector(mock_settings):
    svc = EmbeddingService(mock_settings, pool=None)
    fake_vector = [0.1] * 768
    with patch("litellm.aembedding", AsyncMock(return_value=AsyncMock(data=[AsyncMock(embedding=fake_vector)]))):
        result = await svc.embed("hello world")
    assert len(result) == 768


@pytest.mark.asyncio
async def test_search_returns_node_ids(mock_settings, db):
    svc = EmbeddingService(mock_settings, pool=db)
    # insert a fake embedding
    fake = [0.0] * 768
    fake[0] = 1.0
    vector_str = "[" + ",".join(str(round(v, 6)) for v in fake) + "]"
    await db.execute(
        "INSERT INTO node_embeddings (node_id, embedding) VALUES ($1, $2::vector) ON CONFLICT DO NOTHING",
        999, vector_str,
    )
    query_vec = [0.0] * 768
    query_vec[0] = 0.99
    results = await svc.search(query_vec, limit=1)
    assert 999 in results
