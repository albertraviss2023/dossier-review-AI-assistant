from __future__ import annotations


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["dossiers_loaded"] >= 1200
    assert payload["sections_indexed"] > 0
    assert payload["model_policy"] == "gemma4_only"
    assert payload["system_total_ram_gb"] >= payload["system_available_ram_gb"]


def test_get_dossier_endpoint(client, api_module):
    any_dossier_id = next(iter(api_module.state["dossier_by_id"].keys()))
    response = client.get(f"/v1/dossiers/{any_dossier_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["dossier_id"] == any_dossier_id
    assert "holistic_policy_decision" in payload["labels"]


def test_retrieval_search_endpoint(client):
    response = client.post(
        "/v1/retrieval/search",
        json={"query": "gmp certificate validity and inspection outcome", "top_k": 5},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_hits"] > 0
    assert len(payload["citations"]) <= 5
    assert payload["citations"][0]["citation_id"]
