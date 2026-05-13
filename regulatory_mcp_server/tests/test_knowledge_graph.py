from __future__ import annotations

from regulatory_mcp_server.tools.knowledge_graph import query_knowledge_graph


def test_query_knowledge_graph_returns_focus_subgraph() -> None:
    graph_payload = {
        "nodes": [
            {"id": "DOS-1", "type": "Dossier", "properties": {"recommendation": "approval_granted", "country": "Uganda"}},
            {"id": "manufacturer:Acme Labs", "type": "Manufacturer", "properties": {"name": "Acme Labs"}},
            {"id": "aware:Watch", "type": "AMRCategory", "properties": {"name": "Watch"}},
        ],
        "edges": [
            {"source": "DOS-1", "target": "manufacturer:Acme Labs", "type": "MANUFACTURED_BY", "properties": {}},
            {"source": "DOS-1", "target": "aware:Watch", "type": "HAS_AMR_CATEGORY", "properties": {}},
        ],
    }
    response = query_knowledge_graph(
        question="show manufacturer links for watch antimicrobials",
        graph_payload=graph_payload,
        summary_stats={"total_dossiers": 1, "recommendations": {"approval_granted": 1}},
        max_depth=2,
    )
    assert response["status"] == "success"
    data = response["data"]
    assert data["totals"]["focus_nodes"] >= 1
    assert isinstance(data["focus_subgraph"]["nodes"], list)
    assert isinstance(data["top_connected_entities"], list)

