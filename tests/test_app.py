"""FastAPI surface: /health, and /chat driving the agent loop (scripted model)."""

from __future__ import annotations

import pytest
from _fakes import ScriptedChatModel, tool_call
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from hr_agent.mcp_client import discovery
from hr_agent.web.app import app


@pytest.fixture
def client(monkeypatch):
    """A TestClient with the lifespan run (real stdio MCP discovery)."""
    monkeypatch.setattr(discovery.settings, "mcp_server_url", None)
    with TestClient(app) as c:
        yield c
    app.state.chat_model = None


def test_health_endpoint():
    # No `with`, so lifespan does not run: mcp block present but not connected.
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert set(payload["mcp"]) == {"connected", "tools_discovered", "transport"}
    vs = payload["vector_store"]
    assert set(vs) == {"index_present", "chunks", "embedding_model", "embedding_key_configured"}
    assert payload["retrieval"]["active_method"] in {"vector", "keyword"}


def test_health_reports_mcp_connected_after_lifespan(client):
    payload = client.get("/health").json()
    assert payload["mcp"]["connected"] is True
    assert payload["mcp"]["tools_discovered"] >= 9
    assert payload["mcp"]["transport"] == "stdio"


def test_chat_policy_question_returns_answer(client):
    app.state.chat_model = ScriptedChatModel(
        [
            AIMessage(content="", tool_calls=[tool_call("search_policy_documents", {"query": "pto accrual", "k": 2}, "c1")]),
            AIMessage(content="Full-time employees accrue 10 hours of PTO per month."),
        ]
    )
    payload = client.post("/chat", json={"message": "What is the PTO accrual rate?"}).json()
    assert "10 hours" in payload["answer"]
    assert payload["citations"]
    assert payload["pending_action"] is None


def test_chat_follow_up_keeps_conversation_context(client):
    """A second /chat with the same session_id sees the first turn's messages."""
    model = ScriptedChatModel(
        [
            AIMessage(content="", tool_calls=[tool_call("check_pto_balance", {"employee_id": "E-1002"}, "c1")]),
            AIMessage(content="Marcus Silva (E-1002) has 68 hours of PTO available."),
            AIMessage(content="Carryover is capped at 40 hours into the next year."),
        ]
    )
    app.state.chat_model = model

    first = client.post("/chat", json={"message": "How much PTO does E-1002 have?"}).json()
    sid = first["session_id"]
    assert sid

    second = client.post(
        "/chat", json={"message": "And what about carryover?", "session_id": sid}
    ).json()
    assert second["session_id"] == sid
    assert "40 hours" in second["answer"]

    # The model's second invocation was handed the first turn as history.
    last_call = model.calls[-1]
    contents = [m.content for m in last_call]
    assert "How much PTO does E-1002 have?" in contents
    assert "And what about carryover?" in contents


def test_chat_ticket_request_returns_pending_action(client):
    app.state.chat_model = ScriptedChatModel(
        [AIMessage(content="", tool_calls=[tool_call("create_mock_hr_ticket", {"employee_id": "E-1001", "issue": "laptop"}, "c1")])]
    )
    payload = client.post(
        "/chat",
        json={"message": "File an HR ticket for E-1001 about a laptop."},
    ).json()
    assert payload["pending_action"] is not None
    assert payload["pending_action"]["tool"] == "create_mock_hr_ticket"
    assert "mock action" in payload["answer"].lower()


def test_chat_confirmed_ticket_executes(client):
    app.state.chat_model = ScriptedChatModel(
        [
            AIMessage(content="", tool_calls=[tool_call("create_mock_hr_ticket", {"employee_id": "E-1001", "issue": "laptop"}, "c1")]),
            AIMessage(content="Done - the ticket is filed."),
        ]
    )
    payload = client.post(
        "/chat",
        json={"message": "File an HR ticket for E-1001 about a laptop.", "confirm": True},
    ).json()
    assert payload["pending_action"] is None
    assert payload["answer"] == "Done - the ticket is filed."
    assert any(e["type"] == "tool_call" and e["name"] == "create_mock_hr_ticket" for e in payload["trace"])


def test_health_reflects_mcp_down_after_startup(client, monkeypatch):
    """The /health MCP block is a live probe (cached ~15s), not startup-frozen."""
    from hr_agent.web import app as webapp

    monkeypatch.setattr(discovery.settings, "mcp_server_url", "http://127.0.0.1:1/mcp")
    webapp._mcp_probe.update(at=0.0, value=None)  # force a fresh probe

    payload = client.get("/health").json()
    assert payload["mcp"]["connected"] is False
    assert payload["mcp"]["tools_discovered"] == 0


def test_chat_degrades_to_rag_only_when_mcp_unavailable(monkeypatch):
    async def _boom():
        raise RuntimeError("mcp down")

    monkeypatch.setattr(discovery, "get_tools_async", _boom)
    with TestClient(app) as c:
        payload = c.post("/chat", json={"message": "How much PTO do employees accrue per month?"}).json()
    app.state.chat_model = None

    assert payload["answer"]
    assert payload["citations"]
    assert any(e.get("name") == "rag_only" for e in payload["trace"])


def test_cors_headers_for_local_frontend():
    response = TestClient(app).options(
        "/chat",
        headers={"Origin": "http://localhost:5174", "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5174"
