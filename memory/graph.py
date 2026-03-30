import json
import re
from typing import Any


def _parse_agtype(raw: str) -> Any:
    """Parse AGE agtype string to Python dict/value."""
    if raw is None:
        return None
    raw = re.sub(r"::\w+$", "", str(raw).strip())
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _cypher_ident(s: str) -> str:
    """Backtick-quote a Cypher identifier to prevent injection (openCypher spec: double-backtick escaping)."""
    return f"`{s.replace('`', '``')}`"


def _cypher_literal(v: Any) -> str:
    """Serialize a Python value to a safe Cypher literal string."""
    if v is None:
        return "null"
    elif isinstance(v, bool):
        return "true" if v else "false"
    elif isinstance(v, (int, float)):
        return str(v)
    elif isinstance(v, str):
        # Escape backslashes and single quotes for Cypher string literals
        escaped = v.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
    elif isinstance(v, dict):
        inner = ", ".join(f"`{k.replace(chr(96), chr(92)+chr(96))}`: {_cypher_literal(vv)}" for k, vv in v.items())
        return "{" + inner + "}"
    elif isinstance(v, list):
        return "[" + ", ".join(_cypher_literal(i) for i in v) + "]"
    else:
        return f"'{str(v)}'"


def _props_map(d: dict) -> str:
    """Convert dict to a Cypher inline properties map literal: {k: v, ...}"""
    parts = [f"`{k.replace(chr(96), chr(92)+chr(96))}`: {_cypher_literal(v)}" for k, v in d.items()]
    return "{" + ", ".join(parts) + "}"


class GraphMemory:
    """Graph memory backed by Apache AGE (PostgreSQL extension).

    AGE requires per-connection setup (LOAD + SET search_path) before any
    Cypher queries. Cypher strings must be dollar-quoted literals; bind
    parameters cannot be used for the query string itself.
    """

    def __init__(self, pool) -> None:
        self._pool = pool

    async def _setup_connection(self, conn) -> None:
        await conn.execute("LOAD 'age'")
        await conn.execute('SET search_path = ag_catalog, "$user", public')

    async def _ensure_graph(self, conn) -> None:
        """Create the 'memory' graph if it doesn't exist yet."""
        exists = await conn.fetchval(
            "SELECT count(*) FROM ag_catalog.ag_graph WHERE name = 'memory'"
        )
        if not exists:
            await conn.execute("SELECT create_graph('memory')")

    async def add_node(self, label: str, properties: dict) -> int:
        """Create a new node with the given label and properties, return its AGE id."""
        label_ident = _cypher_ident(label)
        props_lit = _props_map(properties)
        async with self._pool.acquire() as conn:
            await self._setup_connection(conn)
            await self._ensure_graph(conn)
            rows = await conn.fetch(
                f"SELECT result FROM ag_catalog.cypher('memory', $$CREATE (n:{label_ident} {props_lit}) RETURN id(n)$$) AS (result ag_catalog.agtype)"
            )
            return int(_parse_agtype(rows[0]["result"])) if rows else None

    async def merge_node(
        self, label: str, match_key: str, match_val: str, properties: dict
    ) -> int:
        """Create or match node by a unique property; return the node's AGE id."""
        label_ident = _cypher_ident(label)
        match_key_ident = _cypher_ident(match_key)
        match_lit = _cypher_literal(match_val)
        props_lit = _props_map(properties)
        async with self._pool.acquire() as conn:
            await self._setup_connection(conn)
            await self._ensure_graph(conn)
            rows = await conn.fetch(
                f"SELECT nid FROM ag_catalog.cypher('memory', $$MERGE (n:{label_ident} {{{match_key_ident}: {match_lit}}}) SET n += {props_lit} RETURN id(n)$$) AS (nid ag_catalog.agtype)"
            )
            return int(_parse_agtype(rows[0]["nid"])) if rows else None

    async def add_edge(
        self,
        from_id: int,
        relation: str,
        to_id: int,
        properties: dict | None = None,
    ) -> None:
        """Create a directed edge between two nodes by their AGE ids."""
        relation_ident = _cypher_ident(relation)
        props_lit = _props_map(properties) if properties else ""
        async with self._pool.acquire() as conn:
            await self._setup_connection(conn)
            await self._ensure_graph(conn)
            await conn.execute(
                f"SELECT * FROM ag_catalog.cypher('memory', $$MATCH (a), (b) WHERE id(a) = {from_id} AND id(b) = {to_id} CREATE (a)-[r:{relation_ident} {props_lit}]->(b) RETURN r$$) AS (r ag_catalog.agtype)"
            )

    async def delete_node(self, node_id: int) -> None:
        """Delete a node (and all its edges) by AGE id."""
        async with self._pool.acquire() as conn:
            await self._setup_connection(conn)
            await self._ensure_graph(conn)
            await conn.execute(
                f"SELECT * FROM ag_catalog.cypher('memory', $$MATCH (n) WHERE id(n) = {node_id} DETACH DELETE n$$) AS (r ag_catalog.agtype)"
            )

    async def get_nodes_by_label(self, label: str) -> list[dict]:
        """Return all nodes with the given label as a list of property dicts."""
        label_ident = _cypher_ident(label)
        async with self._pool.acquire() as conn:
            await self._setup_connection(conn)
            await self._ensure_graph(conn)
            rows = await conn.fetch(
                f"SELECT props FROM ag_catalog.cypher('memory', $$MATCH (n:{label_ident}) RETURN properties(n)$$) AS (props ag_catalog.agtype)"
            )
            return [_parse_agtype(r["props"]) for r in rows]

    async def get_neighbors(self, node_id: int) -> list[dict]:
        """Return properties of all nodes directly reachable from node_id."""
        async with self._pool.acquire() as conn:
            await self._setup_connection(conn)
            await self._ensure_graph(conn)
            rows = await conn.fetch(
                f"SELECT props FROM ag_catalog.cypher('memory', $$MATCH (a)-[]->(b) WHERE id(a) = {node_id} RETURN properties(b)$$) AS (props ag_catalog.agtype)"
            )
            return [_parse_agtype(r["props"]) for r in rows]

    async def get_subgraph(self, node_id: int, hops: int = 2) -> dict:
        """Return nodes and edges within N hops of a node."""
        async with self._pool.acquire() as conn:
            await self._setup_connection(conn)
            await self._ensure_graph(conn)
            node_id_lit = _cypher_literal(node_id)
            node_rows = await conn.fetch(
                "SELECT n FROM ag_catalog.cypher('memory', $$"
                f"MATCH (start)-[*1..{hops}]-(n) WHERE id(start) = {node_id_lit} RETURN DISTINCT properties(n)"
                "$$) AS (n ag_catalog.agtype)",
            )
            edge_rows = await conn.fetch(
                "SELECT r FROM ag_catalog.cypher('memory', $$"
                f"MATCH (a)-[r]->(b) WHERE id(a) = {node_id_lit} OR id(b) = {node_id_lit} RETURN properties(r)"
                "$$) AS (r ag_catalog.agtype)",
            )
            return {
                "nodes": [_parse_agtype(r["n"]) for r in node_rows],
                "edges": [_parse_agtype(r["r"]) for r in edge_rows],
            }

    async def search_by_ids(self, node_ids: list[int]) -> list[dict]:
        """Fetch properties of nodes by id list (used after pgvector similarity search)."""
        if not node_ids:
            return []
        async with self._pool.acquire() as conn:
            await self._setup_connection(conn)
            await self._ensure_graph(conn)
            results = []
            for nid in node_ids:
                rows = await conn.fetch(
                    f"SELECT props FROM ag_catalog.cypher('memory', $$MATCH (n) WHERE id(n) = {nid} RETURN properties(n)$$) AS (props ag_catalog.agtype)"
                )
                if rows:
                    results.append(_parse_agtype(rows[0]["props"]))
            return results
