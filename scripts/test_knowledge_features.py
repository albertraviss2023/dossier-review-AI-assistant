import requests
import json

BASE_URL = "http://localhost:8000"
LOGIN_PAYLOAD = {"username": "alutakome", "password": "dpar@2026#"}


def _session() -> requests.Session:
    s = requests.Session()
    login = s.post(f"{BASE_URL}/v1/auth/login", json=LOGIN_PAYLOAD, timeout=30)
    login.raise_for_status()
    return s

def test_knowledge_graph(session: requests.Session):
    print("Testing /v1/knowledge-graph...")
    try:
        resp = session.get(f"{BASE_URL}/v1/knowledge-graph", timeout=60)
        resp.raise_for_status()
        data = resp.json()
        print(f"Success: Found {len(data['nodes'])} nodes and {len(data['edges'])} edges.")
        print(f"Summary Stats: {json.dumps(data['summary_stats'], indent=2)}")
        assert "nodes" in data
        assert "summary_stats" in data
    except Exception as e:
        print(f"Failed to connect to API: {e}. (Make sure the server is running)")

def test_visualization_query(session: requests.Session, query: str):
    print(f"\nTesting visualization query: '{query}'")
    try:
        payload = {
            "question": query,
            "workspace": "wiki",
            "dossier_id": None
        }
        resp = session.post(f"{BASE_URL}/v1/assistant/message", json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        print(f"Intent: {data['intent']}")
        if data.get("visualization_data"):
            viz = data["visualization_data"]
            print(f"Visualization Data Found: {viz['type']} - {viz['title']}")
            print(f"Labels: {viz['labels']}")
            print(f"Datasets: {len(viz['datasets'])}")
        else:
            print("No visualization data returned.")
    except Exception as e:
        print(f"Query failed: {e}")

if __name__ == "__main__":
    sess = _session()
    test_knowledge_graph(sess)
    test_visualization_query(sess, "What are the approval trends over the months?")
    test_visualization_query(sess, "Give me a pie chart of approvals vs rejections")
    test_visualization_query(sess, "What are the key AMR concerns?")
    test_visualization_query(sess, "What key violations have been identified?")
