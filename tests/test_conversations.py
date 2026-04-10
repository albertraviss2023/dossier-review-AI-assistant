from __future__ import annotations


def test_linked_conversation_carries_summary_forward(client, api_module):
    dossier_id = next(iter(api_module.state["dossier_by_id"].keys()))
    first = client.post(
        "/v1/conversations",
        json={"title": "Initial thread", "model_id": "gemma-e4b", "dossier_id": dossier_id},
    )
    assert first.status_code == 200
    first_payload = first.json()
    first_id = first_payload["conversation"]["conversation_id"]

    review = client.post(
        "/v1/review",
        json={
            "dossier_id": dossier_id,
            "conversation_id": first_id,
            "model_id": "gemma-e4b",
            "question": "Compare GMP certificate validity with pivotal trial outcome and provide citations.",
            "top_k": 5,
        },
    )
    assert review.status_code == 200

    second = client.post(
        "/v1/conversations",
        json={
            "title": "Linked continuation",
            "linked_from_conversation_id": first_id,
            "model_id": "gemma-e2b",
            "dossier_id": dossier_id,
        },
    )
    assert second.status_code == 200
    second_payload = second.json()
    assert second_payload["conversation"]["linked_from_conversation_id"] == first_id
    assert second_payload["carryover_summary"]
    assert second_payload["conversation"]["carryover_available"] is True


def test_context_window_update_and_auto_compaction(client, api_module):
    dossier_id = next(iter(api_module.state["dossier_by_id"].keys()))
    create = client.post(
        "/v1/conversations",
        json={"title": "Compaction thread", "model_id": "qwen-3.5", "context_window_tokens": 1024, "dossier_id": dossier_id},
    )
    assert create.status_code == 200
    conversation_id = create.json()["conversation"]["conversation_id"]

    long_question = (
        "Compare GMP certificate validity with pivotal trial outcome and stewardship controls "
        "for the dossier while keeping the prior reasoning in view. "
    ) * 60
    review = client.post(
        "/v1/review",
        json={
            "dossier_id": dossier_id,
            "conversation_id": conversation_id,
            "model_id": "qwen-3.5",
            "question": long_question,
            "top_k": 5,
        },
    )
    assert review.status_code == 200
    review_payload = review.json()
    assert review_payload["context_monitor"]["compaction_count"] >= 1

    detail = client.get(f"/v1/conversations/{conversation_id}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["rolling_summary"]
    assert detail_payload["conversation"]["context_monitor"]["usage_ratio"] < 0.98

    update = client.patch(
        f"/v1/conversations/{conversation_id}/context",
        json={"context_window_tokens": 2048},
    )
    assert update.status_code == 200
    update_payload = update.json()
    assert update_payload["conversation"]["context_window_tokens"] == 2048
