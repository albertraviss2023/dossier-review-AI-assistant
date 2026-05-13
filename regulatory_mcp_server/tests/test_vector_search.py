from __future__ import annotations

from regulatory_mcp_server.tools.vector_search import search_vector_database


def test_vector_search_returns_relevant_wiki_chunks():
    result = search_vector_database(
        query="What does WHO AWaRe say about Watch escalation?",
        index="knowledge_wiki",
        filters={},
        top_k=5,
    )
    assert result["status"] == "success"
    assert result["data"]["results"]
    assert any("who-aware-and-glass" in row["metadata"]["citation_id"] for row in result["data"]["results"])


def test_vector_search_filters_by_dossier():
    result = search_vector_database(
        query="patient information leaflet storage warnings",
        index="dossiers",
        filters={"dossier_id": "UPLOAD-STANDARD-001"},
        top_k=5,
    )
    assert result["status"] == "success"
    assert result["data"]["results"]
    assert all(row["metadata"]["dossier_id"] == "UPLOAD-STANDARD-001" for row in result["data"]["results"])


def test_vector_search_returns_empty_results_cleanly():
    result = search_vector_database(
        query="qxzvplm orphan nonce",
        index="knowledge_wiki",
        filters={},
        top_k=3,
    )
    assert result["status"] == "success"
    assert result["data"]["results"] == []
    assert result["warnings"]
