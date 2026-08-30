from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from hr_agent.answering import build_grounded_answer, generate_final_answer, synthesize_final_answer
from hr_agent.mcp_server import build_mcp_server
from hr_agent.routing import route_query
from hr_agent.tools import plan_tool_workflow


def _classify_query(state: dict) -> dict:
    decision = route_query(state["query"])
    state["intent"] = decision["intent"]
    state["reason"] = decision["reason"]
    return state


def _decide_tool_use(state: dict) -> dict:
    tool_plan = plan_tool_workflow(state["query"])
    state["needs_tool"] = tool_plan["needs_tool"]
    state["tool_name"] = tool_plan["tool_name"]
    return state


def _needs_tool_branch(state: dict) -> str:
    return "tool" if state.get("needs_tool") else "answer"


def _extract_employee_id(query: str) -> str | None:
    match = re.search(r"E-\d+", query.upper())
    return match.group(0) if match else None


def _call_mcp_tool(tool_name: str, query: str) -> dict:
    server = build_mcp_server()
    args: dict[str, str] = {}

    if tool_name in {"check_pto_balance", "lookup_employee_profile", "lookup_benefits_status"}:
        employee_id = _extract_employee_id(query)
        if employee_id is None:
            return {"error": "missing_employee_id", "message": "No employee ID was found in the request."}
        args["employee_id"] = employee_id
    elif tool_name == "check_policy_compliance":
        args["question"] = query
    elif tool_name == "create_mock_hr_ticket":
        employee_id = _extract_employee_id(query) or "E-1001"
        args = {"employee_id": employee_id, "issue": query}
    elif tool_name == "draft_hr_email":
        employee_id = _extract_employee_id(query) or "E-1001"
        args = {"employee_id": employee_id, "topic": query}
    else:
        return {"error": "unsupported_tool", "message": f"Tool {tool_name} is not supported in the demo workflow."}

    result = asyncio.run(server.call_tool(tool_name, args))
    if not result:
        return {"error": "empty_tool_result", "message": "The tool returned no data."}

    content = result[0]
    if hasattr(content, "text"):
        try:
            payload = json.loads(content.text)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
        return {"raw": content.text}

    return {"raw": str(result)}


def _tool_response(state: dict) -> dict:
    tool_result = _call_mcp_tool(state["tool_name"], state["query"])
    state["tool_result"] = tool_result
    state["reason"] = state.get("reason", "Tool-based workflow selected.")

    if "error" in tool_result:
        state["answer"] = tool_result["message"]
        state["citations"] = []
        return state

    corpus_dir = Path(__file__).resolve().parents[2] / "corpus"
    answer_data = synthesize_final_answer(state["query"], tool_result=tool_result, corpus_dir=corpus_dir, k=3)
    state["answer"] = answer_data["answer"]
    state["citations"] = answer_data["citations"]
    state["trace"] = answer_data["trace"]
    return state


def _answer_response(state: dict, corpus_dir: str | Path | None = None) -> dict:
    if corpus_dir is None:
        corpus_dir = Path(__file__).resolve().parents[2] / "corpus"

    answer_data = build_grounded_answer(state["query"], corpus_dir=corpus_dir, k=3)
    state["answer"] = answer_data["answer"]
    state["citations"] = answer_data["citations"]
    state["trace"] = answer_data["trace"]
    return state


def build_orchestration_graph() -> StateGraph:
    """Build a minimal LangGraph workflow for the HR policy assistant."""
    workflow = StateGraph(dict)

    workflow.add_node("classify", _classify_query)
    workflow.add_node("decide_tool", _decide_tool_use)
    workflow.add_node("tool_response", _tool_response)
    workflow.add_node("answer", _answer_response)

    workflow.add_edge(START, "classify")
    workflow.add_edge("classify", "decide_tool")
    workflow.add_conditional_edges("decide_tool", _needs_tool_branch, {"tool": "tool_response", "answer": "answer"})
    workflow.add_edge("tool_response", END)
    workflow.add_edge("answer", END)

    return workflow.compile()


def run_workflow(query: str, corpus_dir: str | None = None) -> dict:
    """Execute the orchestration graph for a single user query."""
    graph = build_orchestration_graph()
    result = graph.invoke({"query": query})

    if "citations" not in result:
        result["citations"] = []
    if "tool_name" not in result:
        result["tool_name"] = "none"
    if "needs_tool" not in result:
        result["needs_tool"] = False
    if "intent" not in result:
        result["intent"] = route_query(query)["intent"]

    if corpus_dir is not None and result.get("needs_tool") is False:
        result = _answer_response(result, corpus_dir=corpus_dir)

    if result.get("needs_tool") and result.get("tool_result") is not None and "error" not in result.get("tool_result", {}):
        final = generate_final_answer(
            result["query"],
            tool_result=result["tool_result"],
            corpus_dir=corpus_dir or Path(__file__).resolve().parents[2] / "corpus",
            k=3,
        )
        result["answer"] = final["answer"]
        result["citations"] = final["citations"]
        result["trace"] = final["trace"]

    return result
