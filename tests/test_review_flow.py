from __future__ import annotations


def _model_ids(client):
    payload = client.get("/v1/models").json()
    default_id = payload["default_model_id"]
    available = [model["id"] for model in payload.get("available_models", [])]
    fallback_id = next((mid for mid in available if mid != default_id), default_id)
    return default_id, fallback_id


def test_review_endpoint_returns_grounded_decision(client, api_module):
    dossier_id = next(iter(api_module.state["dossier_by_id"].keys()))
    default_model_id, _ = _model_ids(client)
    conversation = client.post(
        "/v1/conversations",
        json={"title": "Primary review thread", "model_id": default_model_id, "dossier_id": dossier_id},
    ).json()
    response = client.post(
        "/v1/review",
        json={
            "dossier_id": dossier_id,
            "question": "Compare GMP certificate validity with pivotal trial outcome and explain the policy recommendation with citations.",
            "top_k": 5,
            "model_id": default_model_id,
            "conversation_id": conversation["conversation"]["conversation_id"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["dossier_id"] == dossier_id
    assert payload["route"] in {"standard", "fallback"}
    assert payload["recommendation"] in {
        "approval_granted",
        "approval_denied",
        "additional_information_required",
        "abstain",
    }
    assert len(payload["section_diagnostics"]) > 0
    assert payload["selected_model"]["id"] == default_model_id
    assert len(payload["sub_queries"]) >= 3
    assert payload["conversation_id"] == conversation["conversation"]["conversation_id"]
    assert payload["context_monitor"]["context_window_tokens"] == 4096
    assert payload["lineage_tags"]["model_policy"] == "local_multi_model"
    assert payload["lineage_tags"]["model_id"] == default_model_id
    assert payload["memory"]["process_rss_gb"] >= 0.0
    assert "authorization_control" in payload["amr_stewardship"]
    assert "normalized_ingredient" in payload["amr_stewardship"]
    assert "normalization_source" in payload["amr_stewardship"]
    assert "active_moiety" in payload["amr_stewardship"]
    assert "parent_compound" in payload["amr_stewardship"]
    assert "pubchem_cid" in payload["amr_stewardship"]
    assert "chembl_id" in payload["amr_stewardship"]
    assert "unichem_id" in payload["amr_stewardship"]
    assert "chemistry_source" in payload["amr_stewardship"]
    assert payload["amr_stewardship"]["aware_category"] in {"access", "watch", "reserve", "not_applicable"}
    assert payload["amr_stewardship"]["source_mode"] in {"snapshot_backed", "signals_fallback", "live_backed"}
    assert isinstance(payload["amr_stewardship"]["source_trace"], list)


def test_review_endpoint_force_fallback_route(client, api_module):
    dossier_id = next(iter(api_module.state["dossier_by_id"].keys()))
    _, fallback_model_id = _model_ids(client)
    conversation = client.post(
        "/v1/conversations",
        json={"title": "Fallback review thread", "model_id": fallback_model_id, "dossier_id": dossier_id},
    ).json()
    response = client.post(
        "/v1/review",
        json={
            "dossier_id": dossier_id,
            "question": "Provide a policy recommendation.",
            "force_fallback": True,
            "model_id": fallback_model_id,
            "conversation_id": conversation["conversation"]["conversation_id"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["route"] == "fallback"
    assert payload["selected_model"]["id"] == fallback_model_id
    assert payload["lineage_tags"]["route_profile"] == "fallback"
    assert "amr_stewardship" in payload


def test_review_endpoint_abstains_when_no_evidence(client, api_module):
    dossier_id = next(iter(api_module.state["dossier_by_id"].keys()))
    default_model_id, _ = _model_ids(client)
    conversation = client.post(
        "/v1/conversations",
        json={"title": "Sparse evidence thread", "model_id": default_model_id, "dossier_id": dossier_id},
    ).json()
    response = client.post(
        "/v1/review",
        json={
            "dossier_id": dossier_id,
            "question": "zzzxqv qqqnnv unavailableterm1 unavailableterm2",
            "top_k": 5,
            "model_id": default_model_id,
            "conversation_id": conversation["conversation"]["conversation_id"],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["abstained"] is True
    assert payload["recommendation"] == "abstain"
    assert payload["abstain_reason"] in {"insufficient_retrieval_evidence", "faithfulness_gate_failed"}
    assert payload["selected_model"]["id"] == default_model_id
    assert payload["lineage_tags"]["model_id"] == default_model_id
    assert "amr_stewardship" in payload
