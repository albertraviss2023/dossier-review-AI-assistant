from __future__ import annotations

from regulatory_mcp_server.tools.inn_similarity import compute_inn_similarity, fetch_who_inn_candidates


def test_fetch_who_inn_candidates_matches_active_ingredient():
    result = fetch_who_inn_candidates(
        active_ingredient="paracetamol",
        proposed_name="Paracare",
    )
    assert result["status"] == "success"
    assert result["data"]["candidates"]
    assert result["data"]["candidates"][0]["inn"] == "paracetamol"


def test_compute_inn_similarity_flags_high_similarity():
    result = compute_inn_similarity(
        proposed_name="amoxicillin",
        inn_candidates=["amoxicillin"],
        threshold=70,
    )
    assert result["data"]["rule_result"] == "flagged"
    assert result["data"]["decision_effect"] == "cannot_accept_until_resolved"


def test_compute_inn_similarity_passes_lower_similarity():
    result = compute_inn_similarity(
        proposed_name="Paracare",
        inn_candidates=["paracetamol"],
        threshold=70,
    )
    assert result["data"]["rule_result"] == "pass"
    assert result["data"]["decision_effect"] == "can_continue"
