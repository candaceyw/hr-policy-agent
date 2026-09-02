"""Agent loop: LLM (scripted, offline) binds MCP-discovered tools and cycles."""

from __future__ import annotations

import pytest
from _fakes import ScriptedChatModel, tool_call
from langchain_core.messages import AIMessage

from hr_agent.agent.graph import run_agent
from hr_agent.mcp_client import discovery


@pytest.fixture
def mcp_tools(monkeypatch):
    monkeypatch.setattr(discovery.settings, "mcp_server_url", None)
    return discovery.get_tools()


def test_agent_answers_without_tools(mcp_tools):
    model = ScriptedChatModel([AIMessage(content="Full-time staff accrue 10 hours of PTO per month.")])

    result = run_agent("How much PTO do full-time employees accrue?", mcp_tools, model=model)

    assert "10 hours" in result["answer"]
    assert result["iterations"] == 0
    assert result["citations"] == []
    assert [e["type"] for e in result["trace"]] == ["compose"]


def test_agent_calls_a_tool_then_answers(mcp_tools):
    model = ScriptedChatModel(
        [
            AIMessage(content="", tool_calls=[tool_call("list_policy_documents", {}, "c1")]),
            AIMessage(content="There are 17 policy documents in the corpus."),
        ]
    )

    result = run_agent("What policy documents exist?", mcp_tools, model=model)

    assert "17 policy documents" in result["answer"]
    assert result["iterations"] == 1
    types = [e["type"] for e in result["trace"]]
    assert types == ["tool_call", "compose"]
    assert result["trace"][0]["name"] == "list_policy_documents"
    assert result["trace"][0]["result_summary"] == "ok"


def test_agent_collects_citations_from_policy_search(mcp_tools):
    model = ScriptedChatModel(
        [
            AIMessage(
                content="",
                tool_calls=[tool_call("search_policy_documents", {"query": "pto accrual rate", "k": 2}, "c1")],
            ),
            AIMessage(content="Full-time employees accrue 10 hours per month [02-pto-and-vacation-policy]."),
        ]
    )

    result = run_agent("What is the PTO accrual rate?", mcp_tools, model=model)

    assert result["citations"], "expected at least one citation from search_policy_documents"
    assert any("pto" in c["doc_id"] for c in result["citations"])
    assert all({"doc_id", "title", "section", "snippet"} <= set(c) for c in result["citations"])


def test_agent_loop_stops_at_iteration_cap(mcp_tools, monkeypatch):
    monkeypatch.setattr("hr_agent.agent.graph.settings.max_tool_iterations", 3)
    # a model that never stops asking for tools
    forever = [
        AIMessage(content="", tool_calls=[tool_call("list_policy_documents", {}, f"c{i}")])
        for i in range(10)
    ]
    model = ScriptedChatModel(forever)

    result = run_agent("loop forever please", mcp_tools, model=model)

    assert result["iterations"] == 3
    tool_steps = [e for e in result["trace"] if e["type"] == "tool_call"]
    assert len(tool_steps) == 3
    assert "contact HR" in result["answer"]


def test_completion_guard_nudges_a_derailed_model(mcp_tools):
    """A filler reply with no tool calls gets one nudge back into the loop."""
    model = ScriptedChatModel(
        [
            AIMessage(content="Sure thing! Let me know what you need help with."),
            AIMessage(content="", tool_calls=[tool_call("list_policy_documents", {}, "c1")]),
            AIMessage(content="There are 17 policy documents."),
        ]
    )
    result = run_agent("What policy documents exist?", mcp_tools, model=model)

    assert "17 policy documents" in result["answer"]
    assert any(e["type"] == "tool_call" for e in result["trace"])


def test_completion_guard_leaves_a_real_short_answer_alone(mcp_tools):
    model = ScriptedChatModel([AIMessage(content="Full-time staff accrue 10 hours of PTO per month.")])
    result = run_agent("PTO accrual rate?", mcp_tools, model=model)

    assert result["answer"] == "Full-time staff accrue 10 hours of PTO per month."
    assert result["iterations"] == 0


def test_completion_guard_nudges_filler_that_follows_a_tool_call(mcp_tools):
    """A model that calls a tool and then replies with filler still gets nudged."""
    model = ScriptedChatModel(
        [
            AIMessage(content="", tool_calls=[tool_call("list_policy_documents", {}, "c1")]),
            AIMessage(content="I'm ready to help! What HR question do you have?"),
            AIMessage(content="There are 17 policy documents."),
        ]
    )
    result = run_agent("What policy documents exist?", mcp_tools, model=model)

    assert "17 policy documents" in result["answer"]


def test_agent_reports_llm_error_without_crashing(mcp_tools):
    class BoomModel(ScriptedChatModel):
        def _generate(self, *a, **k):
            raise RuntimeError("provider exploded")

    result = run_agent("anything", mcp_tools, model=BoomModel([]))

    assert result["llm_error"] is not None
    assert "provider exploded" in result["llm_error"]
    assert result["answer"]  # a degraded answer, not an exception
