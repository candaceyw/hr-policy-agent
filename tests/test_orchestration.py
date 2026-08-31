"""Orchestration: the agent loop + confirmation gate, plus RAG-only degradation.

All model behaviour is scripted (offline). Tools are the real MCP tools,
discovered over stdio.
"""

from __future__ import annotations

import pytest
from _fakes import ScriptedChatModel, tool_call
from langchain_core.messages import AIMessage

from hr_agent.mcp_client import discovery
from hr_agent.orchestration import run_workflow

TICKET_QUERY = "Create a mock HR ticket for employee E-1001 about a broken laptop."


@pytest.fixture
def mcp_tools(monkeypatch):
    monkeypatch.setattr(discovery.settings, "mcp_server_url", None)
    return discovery.get_tools()


def test_agent_answers_policy_question_with_citations(mcp_tools):
    model = ScriptedChatModel(
        [
            AIMessage(content="", tool_calls=[tool_call("search_policy_documents", {"query": "pto accrual", "k": 2}, "c1")]),
            AIMessage(content="Full-time staff accrue 10 hours per month [02-pto-and-vacation-policy]."),
        ]
    )
    result = run_workflow("What is the PTO accrual rate?", mcp_tools, model=model)

    assert "10 hours" in result["answer"]
    assert result["pending_action"] is None
    assert any(c["doc_id"].startswith("02-pto") for c in result["citations"])
    assert [e["type"] for e in result["trace"]] == ["classify", "tool_call", "compose"]


def test_agent_looks_up_employee_data(mcp_tools):
    model = ScriptedChatModel(
        [
            AIMessage(content="", tool_calls=[tool_call("check_pto_balance", {"employee_id": "E-1002"}, "c1")]),
            AIMessage(content="E-1002 has 68 hours of PTO available."),
        ]
    )
    result = run_workflow("How much PTO does E-1002 have?", mcp_tools, model=model)

    assert "68" in result["answer"]
    call_step = next(e for e in result["trace"] if e["type"] == "tool_call")
    assert call_step["name"] == "check_pto_balance"
    assert call_step["result_summary"] == "ok"


def _ticket_model(*, with_followup: bool) -> ScriptedChatModel:
    script = [AIMessage(content="", tool_calls=[tool_call("create_mock_hr_ticket", {"employee_id": "E-1001", "issue": "broken laptop"}, "c1")])]
    if with_followup:
        script.append(AIMessage(content="I filed the ticket for you."))
    return ScriptedChatModel(script)


def test_ticket_request_without_confirmation_returns_pending_action(mcp_tools):
    result = run_workflow(TICKET_QUERY, mcp_tools, model=_ticket_model(with_followup=False))

    assert result["pending_action"] is not None
    assert result["pending_action"]["tool"] == "create_mock_hr_ticket"
    assert "mock action" in result["answer"].lower()
    assert not any(e["type"] == "tool_call" for e in result["trace"])


def test_ticket_request_declined_does_not_execute(mcp_tools):
    result = run_workflow(TICKET_QUERY, mcp_tools, confirm=False, model=_ticket_model(with_followup=False))

    assert result["pending_action"] is None
    assert "did not" in result["answer"].lower()
    assert any(e["name"] == "confirmation_declined" for e in result["trace"])
    assert not any(e["type"] == "tool_call" for e in result["trace"])


def test_ticket_request_confirmed_executes_tool(mcp_tools):
    result = run_workflow(TICKET_QUERY, mcp_tools, confirm=True, model=_ticket_model(with_followup=True))

    assert result["pending_action"] is None
    call_step = next(e for e in result["trace"] if e["type"] == "tool_call")
    assert call_step["name"] == "create_mock_hr_ticket"
    assert call_step["result_summary"] == "ok"
    assert result["answer"] == "I filed the ticket for you."


def test_agent_chains_multiple_tools_in_order(mcp_tools):
    """The Ireland scenario: policy search -> section -> employee PTO -> answer."""
    model = ScriptedChatModel(
        [
            AIMessage(content="", tool_calls=[tool_call("search_policy_documents", {"query": "international remote work approval", "k": 3}, "c1")]),
            AIMessage(content="", tool_calls=[tool_call("get_policy_section", {"doc_id": "05-out-of-state-and-international-remote-work", "section": "Approval Requirements"}, "c2")]),
            AIMessage(content="", tool_calls=[tool_call("check_pto_balance", {"employee_id": "E-1002"}, "c3")]),
            AIMessage(content="Marcus needs written approval from his manager and People Ops, uses his own equipment abroad, and has 68 hours of PTO available [05-out-of-state-and-international-remote-work]."),
        ]
    )
    result = run_workflow(
        "Marcus Silva wants to work from Ireland for six weeks - approvals, equipment, and PTO?",
        mcp_tools,
        model=model,
    )

    names = [e["name"] for e in result["trace"] if e["type"] == "tool_call"]
    assert names == ["search_policy_documents", "get_policy_section", "check_pto_balance"]
    assert result["trace"][-1]["type"] == "compose"
    assert result["pending_action"] is None
    assert "68 hours" in result["answer"]
    assert any(c["doc_id"].startswith("05-") for c in result["citations"])


def test_degrades_to_rag_only_when_no_tools():
    result = run_workflow("How much PTO do employees accrue per month?", [], corpus_dir="corpus")

    assert result["answer"]
    assert result["citations"]
    assert result["pending_action"] is None
    assert any(e.get("name") == "rag_only" for e in result["trace"])
