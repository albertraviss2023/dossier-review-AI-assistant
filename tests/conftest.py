from __future__ import annotations

import importlib
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def api_module(tmp_path_factory: pytest.TempPathFactory):
    audit_file = tmp_path_factory.mktemp("audit") / "audit.jsonl"
    conversations_file = tmp_path_factory.mktemp("conversations") / "conversations.json"
    uploads_dir = tmp_path_factory.mktemp("uploads")
    auth_state_file = tmp_path_factory.mktemp("auth") / "auth.json"
    governance_state_file = tmp_path_factory.mktemp("governance") / "governance.json"
    os.environ["DOSSIER_AUDIT_LOG"] = str(audit_file)
    os.environ["DOSSIER_CONVERSATIONS_STATE"] = str(conversations_file)
    os.environ["DOSSIER_UPLOADED_DOSSIERS_DIR"] = str(uploads_dir)
    os.environ["DOSSIER_AUTH_STATE_PATH"] = str(auth_state_file)
    os.environ["DOSSIER_GOVERNANCE_STATE_PATH"] = str(governance_state_file)

    import dossier_review_ai_assistant.api as module

    module = importlib.reload(module)
    yield module

    os.environ.pop("DOSSIER_AUDIT_LOG", None)
    os.environ.pop("DOSSIER_CONVERSATIONS_STATE", None)
    os.environ.pop("DOSSIER_UPLOADED_DOSSIERS_DIR", None)
    os.environ.pop("DOSSIER_AUTH_STATE_PATH", None)
    os.environ.pop("DOSSIER_GOVERNANCE_STATE_PATH", None)


@pytest.fixture()
def client(api_module):
    client = TestClient(api_module.app)
    response = client.post(
        "/v1/auth/login",
        json={"username": "alutakome", "password": "dpar@2026#"},
    )
    assert response.status_code == 200
    return client
