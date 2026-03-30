import json
from typing import Any

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "memory_add",
            "description": (
                "Add or update a fact in the knowledge graph as a triple. "
                "Use this when the user shares information worth remembering."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Subject entity (e.g. 'Oleh', 'the user')"},
                    "relation": {"type": "string", "description": "Relation label in UPPER_CASE (e.g. LIVES_IN, LIKES, IS)"},
                    "object": {"type": "string", "description": "Object entity (e.g. 'Berlin', 'Python', 'vegetarian')"},
                    "subject_type": {"type": "string", "description": "Node label for subject: Person|Topic|Fact|Place|Event"},
                    "object_type": {"type": "string", "description": "Node label for object: Person|Topic|Fact|Place|Event"},
                },
                "required": ["subject", "relation", "object", "subject_type", "object_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_search",
            "description": "Search the knowledge graph for relevant nodes using semantic similarity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language query to search memories"},
                    "limit": {"type": "integer", "description": "Max results (default 5)", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_delete",
            "description": "Delete a node from the knowledge graph by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "integer", "description": "The graph node ID to delete"},
                },
                "required": ["node_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_get_context",
            "description": "Get the full subgraph (2 hops) around a subject — everything known about a person or entity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Entity name to look up"},
                },
                "required": ["subject"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information (news, prices, weather, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        },
    },
]


async def execute_tool(
    name: str,
    args: dict,
    *,
    graph,
    embeddings,
    tavily_key: str | None = None,
) -> str:
    """Execute a tool call and return a string result for the model."""
    if name == "memory_add":
        subj_id = await graph.merge_node(
            args["subject_type"], "name", args["subject"],
            {"name": args["subject"], "chat_id": args.get("chat_id", 0)},
        )
        obj_id = await graph.merge_node(
            args["object_type"], "name", args["object"],
            {"name": args["object"]},
        )
        await graph.add_edge(subj_id, args["relation"], obj_id)
        await embeddings.save(subj_id, args["subject"])
        await embeddings.save(obj_id, args["object"])
        return f"Saved: ({args['subject']}) -{args['relation']}-> ({args['object']})"

    if name == "memory_search":
        limit = args.get("limit", 5)
        node_ids = await embeddings.search_text(args["query"], limit=limit)
        nodes = await graph.search_by_ids(node_ids)
        if not nodes:
            return "No relevant memories found."
        return "Memories:\n" + "\n".join(f"- {json.dumps(n)}" for n in nodes)

    if name == "memory_delete":
        await graph.delete_node(int(args["node_id"]))
        return f"Deleted node {args['node_id']}"

    if name == "memory_get_context":
        node_ids = await embeddings.search_text(args["subject"], limit=1)
        if not node_ids:
            return f"No node found for '{args['subject']}'"
        subgraph = await graph.get_subgraph(node_ids[0], hops=2)
        nodes = subgraph.get("nodes", [])
        if not nodes:
            return f"Nothing found about '{args['subject']}'"
        return f"Context for '{args['subject']}':\n" + "\n".join(f"- {json.dumps(n)}" for n in nodes)

    if name == "web_search":
        if not tavily_key:
            return "Web search is not configured (TAVILY_API_KEY missing)."
        from tavily import AsyncTavilyClient  # type: ignore
        client = AsyncTavilyClient(api_key=tavily_key)
        resp = await client.search(args["query"])
        results = resp.get("results", [])[:3]
        if not results:
            return "No results found."
        lines = [f"[{r['title']}]({r['url']})\n{r['content']}" for r in results]
        return "\n\n".join(lines)

    return f"Unknown tool: {name}"
