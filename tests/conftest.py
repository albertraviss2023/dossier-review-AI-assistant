from __future__ import annotations

import importlib
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def api_module(tmp_path_factory: pytest.TempPathFactory):
    audit_file = tmp_path_factory.mktemp("audit") / "audit.jsonl"
    conversations_file = tmp_path_factory.mktemp("conversations") / "conversations.json"
    os.environ["DOSSIER_AUDIT_LOG"] = str(audit_file)
    os.environ["DOSSIER_CONVERSATIONS_STATE"] = str(conversations_file)

    import dossier_review_ai_assistant.api as module

    module = importlib.reload(module)
    yield module

    os.environ.pop("DOSSIER_AUDIT_LOG", None)
    os.environ.pop("DOSSIER_CONVERSATIONS_STATE", None)


@pytest.fixture()
def client(api_module):
    return TestClient(api_module.app)
