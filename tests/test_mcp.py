import asyncio

from hr_agent.mcp_server import build_mcp_server


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
