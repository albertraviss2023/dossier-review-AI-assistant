from __future__ import annotations


def test_review_endpoint_returns_grounded_decision(client, api_module):
    dossier_id = next(iter(api_module.state["dossier_by_id"].keys()))
    conversation = client.post(
        "/v1/conversations",
        json={"title": "Primary review thread", "model_id": "qwen-3.5", "dossier_id": dossier_id},
    ).json()
    response = client.post(
        "/v1/review",
        json={
            "dossier_id": dossier_id,
            "question": "Compare GMP certificate validity with pivotal trial outcome and explain the policy recommendation with citations.",
            "top_k": 5,
            "model_id": "qwen-3.5",
            "conversation_id": conversation["conversation"]["conversation_id"],
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
    assert payload["selected_model"]["id"] == "qwen-3.5"
    assert len(payload["sub_queries"]) >= 3
    assert payload["conversation_id"] == conversation["conversation"]["conversation_id"]
    assert payload["context_monitor"]["context_window_tokens"] == 4096
    assert payload["lineage_tags"]["model_policy"] == "local_multi_model"
    assert payload["lineage_tags"]["model_id"] == "qwen-3.5"
    assert payload["memory"]["process_rss_gb"] >= 0.0
    assert "authorization_control" in payload["amr_stewardship"]
    assert payload["amr_stewardship"]["aware_category"] in {"access", "watch", "reserve", "not_applicable"}


def test_review_endpoint_force_fallback_route(client, api_module):
    dossier_id = next(iter(api_module.state["dossier_by_id"].keys()))
    conversation = client.post(
        "/v1/conversations",
        json={"title": "Fallback review thread", "model_id": "gemma-e2b", "dossier_id": dossier_id},
    ).json()
    response = client.post(
        "/v1/review",
        json={
            "dossier_id": dossier_id,
            "question": "Provide a policy recommendation.",
            "force_fallback": True,
            "model_id": "gemma-e2b",
            "conversation_id": conversation["conversation"]["conversation_id"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["route"] == "fallback"
    assert payload["selected_model"]["id"] == "gemma-e2b"
    assert payload["lineage_tags"]["route_profile"] == "fallback"
    assert "amr_stewardship" in payload


def test_review_endpoint_abstains_when_no_evidence(client, api_module):
    dossier_id = next(iter(api_module.state["dossier_by_id"].keys()))
    conversation = client.post(
        "/v1/conversations",
        json={"title": "Sparse evidence thread", "model_id": "gemma-e4b", "dossier_id": dossier_id},
    ).json()
    response = client.post(
        "/v1/review",
        json={
            "dossier_id": dossier_id,
            "question": "zzzxqv qqqnnv unavailableterm1 unavailableterm2",
            "top_k": 5,
            "model_id": "gemma-e4b",
            "conversation_id": conversation["conversation"]["conversation_id"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["abstained"] is True
    assert payload["recommendation"] == "abstain"
    assert payload["abstain_reason"] in {"insufficient_retrieval_evidence", "faithfulness_gate_failed"}
    assert payload["selected_model"]["id"] == "gemma-e4b"
    assert payload["lineage_tags"]["model_id"] == "gemma-e4b"
    assert "amr_stewardship" in payload
