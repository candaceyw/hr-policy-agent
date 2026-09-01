import asyncio
import json

from hr_agent.mcp_client import discovery
from hr_agent.mcp_server import build_mcp_server, resolve_transport


def _call(tool: str, args: dict) -> dict:
    server = build_mcp_server()
    result = asyncio.run(server.call_tool(tool, args))
    return json.loads(result[0].text)

EXPECTED_TOOLS = {
    "search_policy_documents",
    "get_policy_section",
    "list_policy_documents",
    "check_policy_compliance",
    "lookup_employee_profile",
    "check_pto_balance",
    "lookup_benefits_status",
    "create_mock_hr_ticket",
    "draft_hr_email",
}


def test_mcp_server_discovers_tools():
    server = build_mcp_server()
    tools = asyncio.run(server.list_tools())

    names = {tool.name for tool in tools}
    expected = {
        "search_policy_documents",
        "get_policy_section",
        "list_policy_documents",
        "check_policy_compliance",
        "lookup_employee_profile",
        "check_pto_balance",
        "lookup_benefits_status",
        "create_mock_hr_ticket",
        "draft_hr_email",
    }
    assert expected.issubset(names)
    assert len(names) >= 9


def test_mcp_tool_lookup_employee_profile():
    server = build_mcp_server()
    result = asyncio.run(server.call_tool("lookup_employee_profile", {"employee_id": "E-1001"}))
    payload = __import__("json").loads(result[0].text)
    assert payload["employee_id"] == "E-1001"
    assert payload["name"] == "Alicia Chen"


def test_check_pto_balance_derives_available_hours():
    server = build_mcp_server()
    result = asyncio.run(server.call_tool("check_pto_balance", {"employee_id": "E-1007"}))
    payload = __import__("json").loads(result[0].text)
    # E-1007: 110 accrued - 58 used - 8 pending = 44
    assert payload["available_hours"] == 44.0
    assert isinstance(payload["available_hours"], (int, float))


def test_check_pto_balance_unknown_employee_errors():
    server = build_mcp_server()
    result = asyncio.run(server.call_tool("check_pto_balance", {"employee_id": "E-9999"}))
    payload = __import__("json").loads(result[0].text)
    assert payload["error"] == "not_found"


def test_check_policy_compliance_is_retrieval_backed():
    payload = _call(
        "check_policy_compliance",
        {"question": "Can an employee work remotely from another state for six weeks?"},
    )
    assert payload["status"] == "requires_review"
    assert payload["relevant_sections"], "expected retrieved evidence, not a bare verdict"
    for section in payload["relevant_sections"]:
        assert set(section) == {"doc_id", "section", "snippet"}
        assert section["doc_id"] and section["snippet"]


def test_check_policy_compliance_routine_pto_is_ok():
    payload = _call("check_policy_compliance", {"question": "I want to take PTO next Friday."})
    assert payload["status"] == "ok"
    assert payload["relevant_sections"]


def test_check_policy_compliance_off_corpus_is_not_applicable():
    payload = _call(
        "check_policy_compliance",
        {"question": "What is the airspeed velocity of an unladen swallow?"},
    )
    assert payload["status"] == "not_applicable"
    assert payload["relevant_sections"] == []


def test_create_mock_hr_ticket_has_unique_deterministic_id_and_sample_shape():
    a = _call("create_mock_hr_ticket", {"employee_id": "E-1001", "issue": "broken laptop screen"})
    b = _call("create_mock_hr_ticket", {"employee_id": "E-1001", "issue": "broken laptop screen"})
    c = _call("create_mock_hr_ticket", {"employee_id": "E-1001", "issue": "missing paycheck"})

    assert a["ticket_id"] == b["ticket_id"], "same inputs must be deterministic"
    assert a["ticket_id"] != c["ticket_id"], "different issues must not collide"
    assert a["ticket_id"].startswith("HR-")
    assert a["status"] == "created_mock"
    assert a["category"] == "equipment"
    assert c["category"] == "payroll"
    assert a["summary"] and a["created_at"].endswith("Z")


def test_draft_hr_email_interpolates_topic_and_employee():
    pto = _call("draft_hr_email", {"employee_id": "E-1001", "topic": "carrying over unused PTO"})
    remote = _call("draft_hr_email", {"employee_id": "E-1001", "topic": "working from Ireland"})

    assert pto["draft"] != remote["draft"], "draft must depend on the topic"
    assert "carrying over unused PTO" in pto["draft"]
    assert "Hi Alicia," in pto["draft"], "known employee id resolves to a first name"
    assert "E-1001" in pto["draft"]


def test_list_policy_documents_returns_doc_id_title_pairs():
    payload = _call("list_policy_documents", {})
    docs = payload["documents"]
    assert docs and all(set(d) == {"doc_id", "title"} for d in docs)
    sample = docs[0]
    assert "-" not in sample["title"] or sample["title"][0].isupper()


def test_resolve_transport_defaults_to_stdio():
    assert resolve_transport(http_flag=False, configured="stdio") == "stdio"
    assert resolve_transport(http_flag=False, configured="") == "stdio"


def test_resolve_transport_opts_into_http():
    assert resolve_transport(http_flag=True, configured="stdio") == "streamable-http"
    assert resolve_transport(http_flag=False, configured="streamable-http") == "streamable-http"
    assert resolve_transport(http_flag=False, configured=" HTTP ") == "streamable-http"


def test_build_mcp_server_uses_supplied_host_port():
    server = build_mcp_server(host="0.0.0.0", port=9999)
    assert server.settings.host == "0.0.0.0"
    assert server.settings.port == 9999


def test_connection_switches_on_mcp_server_url(monkeypatch):
    monkeypatch.setattr(discovery.settings, "mcp_server_url", None)
    stdio = discovery._connections()["hr"]
    assert stdio["transport"] == "stdio"
    assert stdio["args"] == ["-m", "hr_agent.mcp_server"]
    assert discovery.active_transport() == "stdio"

    monkeypatch.setattr(discovery.settings, "mcp_server_url", "http://127.0.0.1:8765/mcp")
    http = discovery._connections()["hr"]
    assert http["transport"] == "streamable_http"
    assert http["url"] == "http://127.0.0.1:8765/mcp"
    assert discovery.active_transport() == "streamable_http"


def test_discovery_lists_tools_over_stdio(monkeypatch):
    """Integration: spawn the server over stdio and discover its tools."""
    monkeypatch.setattr(discovery.settings, "mcp_server_url", None)
    tools = discovery.get_tools()

    names = {tool.name for tool in tools}
    assert EXPECTED_TOOLS.issubset(names)
    assert len(names) >= 9
    # every discovered tool carries a non-empty input schema
    for tool in tools:
        assert tool.args_schema is not None


def test_discovery_health_connected_over_stdio(monkeypatch):
    monkeypatch.setattr(discovery.settings, "mcp_server_url", None)
    report = discovery.health()
    assert report["connected"] is True
    assert report["tools_discovered"] >= 9
    assert report["transport"] == "stdio"


def test_discovery_health_degrades_when_server_unreachable(monkeypatch):
    monkeypatch.setattr(discovery.settings, "mcp_server_url", "http://127.0.0.1:1/mcp")
    report = discovery.health()
    assert report["connected"] is False
    assert report["tools_discovered"] == 0
    assert report["transport"] == "streamable_http"


def test_app_lifespan_discovers_tools_for_health(monkeypatch):
    """Running the FastAPI lifespan populates the real /health mcp block."""
    from fastapi.testclient import TestClient

    from hr_agent.web.app import app

    monkeypatch.setattr(discovery.settings, "mcp_server_url", None)
    with TestClient(app) as client:  # `with` runs startup/shutdown
        payload = client.get("/health").json()

    assert payload["mcp"]["connected"] is True
    assert payload["mcp"]["tools_discovered"] >= 9
    assert payload["mcp"]["transport"] == "stdio"
