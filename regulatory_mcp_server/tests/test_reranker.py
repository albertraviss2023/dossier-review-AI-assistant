from __future__ import annotations

from regulatory_mcp_server.tools.reranker import rerank_search_results


def test_reranker_prioritizes_direct_regulatory_match():
    result = rerank_search_results(
        query="missing patient information warnings and contraindications",
        candidate_results=[
            {
                "chunk_id": "generic-1",
                "source": "knowledge_wiki",
                "text": "General review workflow and high-level discussion of approval outcomes.",
                "score": 0.91,
                "metadata": {"section_title": "Workflow Overview"},
            },
            {
                "chunk_id": "pil-1",
                "source": "dossier_section",
                "text": "The patient information leaflet omits contraindications and warnings for special populations.",
                "score": 0.78,
                "metadata": {"section_title": "Patient Information Leaflet", "section_id": "pil-1"},
            },
        ],
        rerank_criteria=[
            "regulatory relevance",
            "section specificity",
            "current dossier applicability",
        ],
        top_k=2,
    )
    rows = result["data"]["reranked_results"]
    assert rows[0]["chunk_id"] == "pil-1"
    assert "current dossier applicability" in rows[0]["reason"]


def test_reranker_respects_top_k():
    result = rerank_search_results(
        query="gmp certificate validity",
        candidate_results=[
            {
                "chunk_id": "g1",
                "source": "dossier_section",
                "text": "The GMP certificate is valid until 2027.",
                "score": 0.7,
                "metadata": {"section_title": "Manufacturer and GMP Evidence", "section_id": "m1_gmp"},
            },
            {
                "chunk_id": "g2",
                "source": "knowledge_wiki",
                "text": "GMP evidence should include current certificates and inspection history.",
                "score": 0.69,
                "metadata": {"section_title": "GMP Guidance"},
            },
        ],
        rerank_criteria=["regulatory relevance"],
        top_k=1,
    )
    assert len(result["data"]["reranked_results"]) == 1


def test_reranker_handles_empty_candidates():
    result = rerank_search_results(
        query="gmp certificate validity",
        candidate_results=[],
        rerank_criteria=["regulatory relevance"],
        top_k=5,
    )
    assert result["status"] == "success"
    assert result["data"]["reranked_results"] == []
    assert result["warnings"]
