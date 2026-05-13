
from starlette.testclient import TestClient
from dossier_review_ai_assistant.api import app, state
import os

def test_repro_value_error():
    client = TestClient(app)
    # Ensure we have a dossier in state
    if not state["dossier_by_id"]:
        print("No dossiers in state, cannot run repro")
        return
    
    any_dossier_id = next(iter(state["dossier_by_id"].keys()))
    
    response = client.post(
        "/v1/assistant/message",
        json={
            "workspace": "review",
            "question": "What are the key issues?",
            "dossier_id": any_dossier_id
        }
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 500:
        print(response.text)
    else:
        print("Success or non-500 error")

if __name__ == "__main__":
    test_repro_value_error()
