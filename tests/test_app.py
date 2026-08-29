from fastapi.testclient import TestClient

from hr_agent.orchestration import build_orchestration_graph, run_workflow
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


def test_cors_headers_for_local_frontend():
    client = TestClient(app)
    response = client.options(
        "/chat",
        headers={
            "Origin": "http://localhost:5174",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5174"


def test_langgraph_workflow_returns_structured_answer():
    graph = build_orchestration_graph()
    result = graph.invoke({"query": "How much PTO do employees accrue per month?"})
    assert result["intent"] == "policy_question"
    assert result["needs_tool"] is False
    assert "answer" in result
    assert result["answer"]
    assert result["citations"]

    result_dict = run_workflow("How much PTO do employees accrue per month?")
    assert result_dict["intent"] == "policy_question"
    assert result_dict["needs_tool"] is False
