from __future__ import annotations


def test_review_endpoint_returns_grounded_decision(client, api_module):
    dossier_id = next(iter(api_module.state["dossier_by_id"].keys()))
    response = client.post(
        "/v1/review",
        json={
            "dossier_id": dossier_id,
            "question": "Assess GMP certificate validity and pivotal trial outcome with citations.",
            "top_k": 5,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["dossier_id"] == dossier_id
    assert payload["route"] in {"standard", "fallback"}
    assert payload["recommendation"] in {
        "fast_track",
        "standard_review",
        "deep_review",
        "reject_and_return",
        "abstain",
    }
    assert len(payload["section_diagnostics"]) > 0
    assert payload["lineage_tags"]["model_policy"] == "gemma4_only"
    assert payload["memory"]["process_rss_gb"] >= 0.0


def test_review_endpoint_force_fallback_route(client, api_module):
    dossier_id = next(iter(api_module.state["dossier_by_id"].keys()))
    response = client.post(
        "/v1/review",
        json={
            "dossier_id": dossier_id,
            "question": "Provide a policy recommendation.",
            "force_fallback": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["route"] == "fallback"
    assert payload["lineage_tags"]["route_profile"] == "fallback"


def test_review_endpoint_abstains_when_no_evidence(client, api_module):
    dossier_id = next(iter(api_module.state["dossier_by_id"].keys()))
    response = client.post(
        "/v1/review",
        json={
            "dossier_id": dossier_id,
            "question": "zzzxqv qqqnnv unavailableterm1 unavailableterm2",
            "top_k": 5,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["abstained"] is True
    assert payload["recommendation"] == "abstain"
    assert payload["abstain_reason"] in {"insufficient_retrieval_evidence", "faithfulness_gate_failed"}
    assert payload["lineage_tags"]["model_id"] == "ai/gemma4:4B-Q4_K_XL"
