from fastapi.testclient import TestClient

from hr_agent.web.app import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "mcp" in payload
    assert "vector_store" in payload


def test_chat_endpoint_returns_answer():
    client = TestClient(app)
    response = client.post("/chat", json={"message": "How much PTO do employees accrue per month?"})
    assert response.status_code == 200
    payload = response.json()
    assert "answer" in payload
    assert payload["answer"]
