from __future__ import annotations


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["dossiers_loaded"] >= 1200
    assert payload["sections_indexed"] > 0
    assert payload["model_policy"] == "local_multi_model"
    assert payload["default_model_id"] == "gemma-e4b"
    assert payload["default_context_window_tokens"] == 4096
    assert len(payload["available_models"]) >= 3
    assert payload["system_total_ram_gb"] >= payload["system_available_ram_gb"]


def test_model_catalog_endpoint(client):
    response = client.get("/v1/models")
    assert response.status_code == 200
    payload = response.json()
    assert payload["default_model_id"] == "gemma-e4b"
    assert {model["id"] for model in payload["available_models"]} >= {
        "gemma-e4b",
        "gemma-e2b",
        "qwen-3.5",
    }


def test_list_dossiers_endpoint(client):
    response = client.get("/v1/dossiers?limit=5")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_items"] == 5
    assert len(payload["items"]) == 5
    assert payload["items"][0]["dossier_id"]
    assert payload["items"][0]["product_name"]


def test_get_dossier_endpoint(client, api_module):
    any_dossier_id = next(iter(api_module.state["dossier_by_id"].keys()))
    response = client.get(f"/v1/dossiers/{any_dossier_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["dossier_id"] == any_dossier_id
    assert "holistic_policy_decision" in payload["labels"]
    assert "aware_category" in payload["policy_signals"]


def test_retrieval_search_endpoint(client):
    response = client.post(
        "/v1/retrieval/search",
        json={"query": "Compare GMP certificate validity with pivotal trial outcome", "top_k": 5},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total_hits"] > 0
    assert len(payload["citations"]) <= 5
    assert payload["citations"][0]["citation_id"]
    assert len(payload["sub_queries"]) >= 3


def test_knowledge_wiki_endpoints(client):
    list_response = client.get("/v1/knowledge-wiki")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total_pages"] >= 4
    assert any(page["page_id"] == "who-aware-and-glass" for page in list_payload["pages"])

    search_response = client.post(
        "/v1/knowledge-wiki/search",
        json={"query": "Reserve fast-track and Watch restriction", "top_k": 5},
    )
    assert search_response.status_code == 200
    search_payload = search_response.json()
    assert search_payload["total_hits"] > 0
    assert len(search_payload["sub_queries"]) >= 3
    assert all(citation["dossier_id"] == "knowledge_wiki" for citation in search_payload["citations"])


def test_conversation_endpoints(client):
    create_response = client.post(
        "/v1/conversations",
        json={"title": "AMR review continuity", "model_id": "gemma-e2b", "context_window_tokens": 4096},
    )
    assert create_response.status_code == 200
    create_payload = create_response.json()
    assert create_payload["conversation"]["title"] == "AMR review continuity"
    assert create_payload["conversation"]["selected_model_id"] == "gemma-e2b"
    assert create_payload["conversation"]["context_monitor"]["context_window_tokens"] == 4096

    list_response = client.get("/v1/conversations")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload["total_items"] >= 1
    assert any(item["conversation_id"] == create_payload["conversation"]["conversation_id"] for item in list_payload["items"])
