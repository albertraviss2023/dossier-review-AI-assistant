from __future__ import annotations

import logging
from collections import deque
from typing import Any

from regulatory_mcp_server.app import mcp

from .common import build_tool_envelope, tool_audit


LOGGER = logging.getLogger("regulatory_mcp_server.tools.knowledge_graph")


def _node_label(node: dict[str, Any]) -> str:
    props = node.get("properties", {})
    return str(
        props.get("name")
        or props.get("product_name")
        or props.get("username")
        or props.get("recommendation")
        or node.get("id", "unknown")
    )


@mcp.tool(
    name="query_knowledge_graph",
    description="Walk a dossier knowledge graph and return query-focused subgraph insights (neighbors, paths, and top connected entities).",
)
@tool_audit(tool_name="query_knowledge_graph", logger=LOGGER)
def query_knowledge_graph(
    question: str,
    graph_payload: dict[str, Any],
    summary_stats: dict[str, Any] | None = None,
    max_depth: int = 2,
    max_nodes: int = 60,
) -> dict[str, Any]:
    payload = {
        "question": question,
        "graph_payload": graph_payload,
        "summary_stats": summary_stats or {},
        "max_depth": max_depth,
        "max_nodes": max_nodes,
    }
    nodes = list(graph_payload.get("nodes", []))
    edges = list(graph_payload.get("edges", []))
    node_by_id = {str(node.get("id")): node for node in nodes}
    adjacency: dict[str, list[tuple[str, str]]] = {}
    for edge in edges:
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        rel = str(edge.get("type", "RELATES_TO"))
        if not source or not target:
            continue
        adjacency.setdefault(source, []).append((target, rel))
        adjacency.setdefault(target, []).append((source, rel))

    lowered = question.lower()
    query_terms = {token for token in lowered.replace("/", " ").replace("-", " ").split() if len(token) > 2}
    start_ids: list[str] = []
    for node_id, node in node_by_id.items():
        blob = f"{node_id} {node.get('type', '')} {_node_label(node)} {node.get('properties', {})}".lower()
        if any(term in blob for term in query_terms):
            start_ids.append(node_id)
    if not start_ids:
        start_ids = [nid for nid, node in node_by_id.items() if str(node.get("type")) == "Dossier"][:5]

    visited: set[str] = set()
    frontier = deque([(nid, 0) for nid in start_ids[:8]])
    walked_nodes: list[str] = []
    walked_edges: list[dict[str, Any]] = []
    while frontier and len(visited) < max_nodes:
        current, depth = frontier.popleft()
        if current in visited:
            continue
        visited.add(current)
        walked_nodes.append(current)
        if depth >= max_depth:
            continue
        for nxt, rel in adjacency.get(current, []):
            walked_edges.append({"source": current, "target": nxt, "type": rel})
            if nxt not in visited:
                frontier.append((nxt, depth + 1))

    degree_counts = {
        node_id: len(adjacency.get(node_id, []))
        for node_id in walked_nodes
    }
    top_connected = sorted(degree_counts.items(), key=lambda item: item[1], reverse=True)[:10]

    focus_subgraph = {
        "nodes": [node_by_id[node_id] for node_id in walked_nodes if node_id in node_by_id],
        "edges": walked_edges,
    }
    top_connected_rows = [
        {
            "node_id": node_id,
            "node_type": str(node_by_id.get(node_id, {}).get("type", "Unknown")),
            "label": _node_label(node_by_id.get(node_id, {})),
            "degree": degree,
        }
        for node_id, degree in top_connected
    ]

    summary_stats = summary_stats or {}
    return build_tool_envelope(
        tool_name="query_knowledge_graph",
        payload=payload,
        data={
            "start_nodes": start_ids[:8],
            "focus_subgraph": focus_subgraph,
            "top_connected_entities": top_connected_rows,
            "totals": {
                "nodes": len(nodes),
                "edges": len(edges),
                "focus_nodes": len(focus_subgraph["nodes"]),
                "focus_edges": len(focus_subgraph["edges"]),
            },
            "summary_snapshot": {
                "total_dossiers": int(summary_stats.get("total_dossiers", 0)),
                "recommendations": summary_stats.get("recommendations", {}),
                "aware_categories": summary_stats.get("aware_categories", {}),
                "countries": summary_stats.get("countries", {}),
            },
        },
        warnings=[],
        source_refs=[{"source": "runtime_knowledge_graph_payload", "source_type": "runtime"}],
    )

