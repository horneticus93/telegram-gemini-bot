import pytest
from memory.graph import GraphMemory


@pytest.fixture
async def graph(pool):
    """GraphMemory uses pool.acquire() internally — must receive a pool, not a connection."""
    g = GraphMemory(pool)
    yield g
    # cleanup all test nodes
    async with pool.acquire() as conn:
        await conn.execute("LOAD 'age'")
        await conn.execute('SET search_path = ag_catalog, "$user", public')
        await conn.execute(
            "SELECT * FROM ag_catalog.cypher('memory', $$ MATCH (n) DETACH DELETE n $$) AS (r ag_catalog.agtype)"
        )


@pytest.mark.asyncio
async def test_add_and_search_node(graph):
    node_id = await graph.add_node("Person", {"name": "Oleh"})
    assert node_id is not None
    nodes = await graph.get_nodes_by_label("Person")
    assert any(n["name"] == "Oleh" for n in nodes)


@pytest.mark.asyncio
async def test_add_edge(graph):
    id1 = await graph.add_node("Person", {"name": "Oleh"})
    id2 = await graph.add_node("Place", {"name": "Kyiv"})
    await graph.add_edge(id1, "LIVES_IN", id2)
    neighbors = await graph.get_neighbors(id1)
    assert any(n["name"] == "Kyiv" for n in neighbors)


@pytest.mark.asyncio
async def test_merge_deduplicates(graph):
    id1 = await graph.merge_node("Person", "name", "Oleh", {"name": "Oleh"})
    id2 = await graph.merge_node("Person", "name", "Oleh", {"name": "Oleh"})
    assert id1 == id2  # same node, not a duplicate


@pytest.mark.asyncio
async def test_delete_node(graph):
    node_id = await graph.add_node("Fact", {"text": "temp fact"})
    await graph.delete_node(node_id)
    nodes = await graph.get_nodes_by_label("Fact")
    assert not any(n.get("text") == "temp fact" for n in nodes)
