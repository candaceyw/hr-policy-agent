import asyncio

from hr_agent.mcp_client import discovery
from hr_agent.mcp_server import build_mcp_server, resolve_transport

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
