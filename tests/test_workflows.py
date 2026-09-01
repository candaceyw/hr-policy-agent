"""End-to-end tests for the two demo workflows against the vibespec acceptance
criteria (lines 140-146). Model behaviour is scripted; the MCP tools are real
and discovered over stdio.
"""

from __future__ import annotations

import pytest
from _fakes import ScriptedChatModel, tool_call
from langchain_core.messages import AIMessage

from hr_agent.mcp_client import discovery
from hr_agent.orchestration import run_workflow


@pytest.fixture
def mcp_tools(monkeypatch):
    monkeypatch.setattr(discovery.settings, "mcp_server_url", None)
    return discovery.get_tools()


def _trace_tool_names(result: dict) -> list[str]:
    return [e["name"] for e in result["trace"] if e["type"] == "tool_call"]


def test_remote_work_eligibility_workflow(mcp_tools):
    """AC 140: >=2 distinct policy docs + lookup_employee_profile + check_policy_compliance."""
    model = ScriptedChatModel(
        [
            AIMessage(content="", tool_calls=[tool_call(
                "search_policy_documents",
                {"query": "remote work eligibility out of state approval", "k": 3},
                "c1",
            )]),
            AIMessage(content="", tool_calls=[tool_call(
                "lookup_employee_profile", {"employee_id": "E-1002"}, "c2",
            )]),
            AIMessage(content="", tool_calls=[tool_call(
                "check_policy_compliance",
                {"question": "Can this employee work remotely from another state for six weeks?"},
                "c3",
            )]),
            AIMessage(content="", tool_calls=[tool_call(
                "search_policy_documents",
                {"query": "data security remote access device classification", "k": 3},
                "c4",
            )]),
            AIMessage(content=(
                "Marcus Silva (E-1002) may work remotely from another state with written "
                "manager and People Ops approval [04-remote-and-hybrid-work-policy]; an "
                "out-of-state stay over 30 days triggers a tax/registration review "
                "[05-out-of-state-and-international-remote-work]."
            )),
        ]
    )
    result = run_workflow(
        "Is Marcus Silva (E-1002) eligible to work remotely from another state for six weeks?",
        mcp_tools,
        model=model,
    )

    names = _trace_tool_names(result)
    assert "lookup_employee_profile" in names
    assert "check_policy_compliance" in names
    distinct_docs = {c["doc_id"] for c in result["citations"]}
    assert len(distinct_docs) >= 2, distinct_docs
    assert result["pending_action"] is None
    assert result["trace"][0]["type"] == "classify"
    assert result["intent"] == "agentic_workflow"


def test_pto_request_workflow_has_no_side_effects(mcp_tools):
    """AC 141: check_pto_balance + PTO policy retrieval, and no ticket/email is created."""
    model = ScriptedChatModel(
        [
            AIMessage(content="", tool_calls=[tool_call(
                "check_pto_balance", {"employee_id": "E-1002"}, "c1",
            )]),
            AIMessage(content="", tool_calls=[tool_call(
                "search_policy_documents",
                {"query": "PTO request manager approval advance notice", "k": 2},
                "c2",
            )]),
            AIMessage(content=(
                "You have 68 hours of PTO available, so three days (24 hours) is covered. "
                "Request it through your manager with advance notice "
                "[02-pto-and-vacation-policy]."
            )),
        ]
    )
    result = run_workflow(
        "Can I take three days of PTO next week? My employee id is E-1002.",
        mcp_tools,
        model=model,
    )

    names = _trace_tool_names(result)
    assert "check_pto_balance" in names
    assert "create_mock_hr_ticket" not in names
    assert "draft_hr_email" not in names
    assert any(c["doc_id"].startswith("02-pto") for c in result["citations"])
    assert result["pending_action"] is None
    assert not any(e["type"] == "confirmation" for e in result["trace"])


def test_pto_request_without_an_employee_id_asks_one_clarifying_question(mcp_tools):
    """AC 143/574: no id anywhere -> exactly one clarifying question, no tools, no guess."""
    model = ScriptedChatModel([])  # must never be called
    result = run_workflow("How much PTO do I have left?", mcp_tools, model=model)

    assert [e["type"] for e in result["trace"]] == ["classify", "clarify"]
    assert "employee id" in result["answer"].lower()
    assert result["citations"] == []
    assert result["pending_action"] is None
    assert not _trace_tool_names(result)


def test_unknown_employee_id_is_not_fabricated(mcp_tools):
    """AC 574: E-9999 -> redirect, not an invented profile."""
    model = ScriptedChatModel([])
    result = run_workflow("Show me the employee profile for E-9999.", mcp_tools, model=model)

    assert [e["type"] for e in result["trace"]] == ["classify", "clarify"]
    assert "E-9999" in result["answer"]
    assert not _trace_tool_names(result)
