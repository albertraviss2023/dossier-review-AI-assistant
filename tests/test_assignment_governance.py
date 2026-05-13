from __future__ import annotations


def test_manager_can_assign_and_reviewer_scope_isolation(client):
    client.post("/v1/auth/logout")
    manager_login = client.post("/v1/auth/login", json={"username": "dachan", "password": "123456"})
    assert manager_login.status_code == 200

    create_reviewer_x = client.post(
        "/v1/admin/users",
        json={
            "display_name": "Reviewer X",
            "username": "revx",
            "password": "123456",
            "role": "reviewer",
            "process_scopes": ["marketing_authorization", "clinical_trial"],
        },
    )
    assert create_reviewer_x.status_code in {200, 409}

    create_reviewer_y = client.post(
        "/v1/admin/users",
        json={
            "display_name": "Reviewer Y",
            "username": "revy",
            "password": "123456",
            "role": "reviewer",
            "process_scopes": ["marketing_authorization", "clinical_trial"],
        },
    )
    assert create_reviewer_y.status_code in {200, 409}

    unassigned = client.get("/v1/admin/dossiers/unassigned")
    assert unassigned.status_code == 200
    items = unassigned.json()["items"]
    assert items
    dossier_id = items[0]["dossier_id"]

    assign = client.post(
        f"/v1/admin/dossiers/{dossier_id}/assign",
        json={"reviewer_username": "revx"},
    )
    assert assign.status_code == 200

    client.post("/v1/auth/logout")
    revx_login = client.post("/v1/auth/login", json={"username": "revx", "password": "123456"})
    assert revx_login.status_code == 200
    revx_listing = client.get("/v1/dossiers?limit=200")
    assert revx_listing.status_code == 200
    assert any(item["dossier_id"] == dossier_id for item in revx_listing.json()["items"])

    client.post("/v1/auth/logout")
    revy_login = client.post("/v1/auth/login", json={"username": "revy", "password": "123456"})
    assert revy_login.status_code == 200
    blocked = client.get(f"/v1/dossiers/{dossier_id}")
    assert blocked.status_code == 403


def test_manager_natural_language_performance_query_returns_manager_intent(client):
    client.post("/v1/auth/logout")
    manager_login = client.post("/v1/auth/login", json={"username": "dachan", "password": "123456"})
    assert manager_login.status_code == 200

    response = client.post(
        "/v1/assistant/message",
        json={
            "workspace": "review",
            "question": "who is the slowest reviewer and what is the overall ToT?",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "manager_analytics"


def test_seeded_reviewer_pool_and_assignment_with_manager_dachan(client):
    client.post("/v1/auth/logout")
    manager_login = client.post("/v1/auth/login", json={"username": "dachan", "password": "123456"})
    assert manager_login.status_code == 200

    users_response = client.get("/v1/admin/users")
    assert users_response.status_code == 200
    usernames = {item["username"] for item in users_response.json()["items"]}
    assert {"alutakome", "namayanja", "kaggwa"}.issubset(usernames)

    unassigned = client.get("/v1/admin/dossiers/unassigned")
    assert unassigned.status_code == 200
    items = unassigned.json()["items"]
    assert items
    dossier_id = items[0]["dossier_id"]

    assign = client.post(
        f"/v1/admin/dossiers/{dossier_id}/assign",
        json={"reviewer_username": "namayanja"},
    )
    assert assign.status_code == 200
    assigned_payload = assign.json()
    assert assigned_payload["assigned_reviewer"] == "namayanja"


def test_reviewer_cannot_create_dossier_conversation_for_unassigned_dossier(client):
    client.post("/v1/auth/logout")
    manager_login = client.post("/v1/auth/login", json={"username": "dachan", "password": "123456"})
    assert manager_login.status_code == 200

    create_reviewer_x = client.post(
        "/v1/admin/users",
        json={
            "display_name": "Reviewer X",
            "username": "revx",
            "password": "123456",
            "role": "reviewer",
            "process_scopes": ["marketing_authorization", "clinical_trial"],
        },
    )
    assert create_reviewer_x.status_code in {200, 409}

    create_reviewer_y = client.post(
        "/v1/admin/users",
        json={
            "display_name": "Reviewer Y",
            "username": "revy",
            "password": "123456",
            "role": "reviewer",
            "process_scopes": ["marketing_authorization", "clinical_trial"],
        },
    )
    assert create_reviewer_y.status_code in {200, 409}

    unassigned = client.get("/v1/admin/dossiers/unassigned")
    assert unassigned.status_code == 200
    items = unassigned.json()["items"]
    assert items
    dossier_id = items[0]["dossier_id"]

    assign = client.post(
        f"/v1/admin/dossiers/{dossier_id}/assign",
        json={"reviewer_username": "revx"},
    )
    assert assign.status_code == 200

    client.post("/v1/auth/logout")
    revy_login = client.post("/v1/auth/login", json={"username": "revy", "password": "123456"})
    assert revy_login.status_code == 200
    create_conv = client.post("/v1/conversations", json={"dossier_id": dossier_id})
    assert create_conv.status_code == 403
