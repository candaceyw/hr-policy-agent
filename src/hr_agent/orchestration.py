from __future__ import annotations

from hr_agent.answering import build_grounded_answer
from hr_agent.retrieval import retrieve
from hr_agent.routing import route_query
from hr_agent.tools import plan_tool_workflow


def run_workflow(query: str, corpus_dir: str | None = None) -> dict:
    """A tiny orchestration layer for learning.

    This demonstrates how a simple workflow layers together:
    1. classify intent
    2. decide if a tool is needed
    3. retrieve relevant policy text when appropriate
    4. return a structured result
    """
    decision = route_query(query)
    tool_plan = plan_tool_workflow(query)

    if tool_plan["needs_tool"]:
        return {
            "intent": decision["intent"],
            "needs_tool": True,
            "tool_name": tool_plan["tool_name"],
            "answer": "This request requires a compliance check against the expense policy before a final answer can be given.",
            "citations": [],
            "reason": tool_plan["reason"],
        }

    if corpus_dir is None:
        from pathlib import Path
        corpus_dir = Path(__file__).resolve().parents[2] / "corpus"

    answer_data = build_grounded_answer(query, corpus_dir=corpus_dir, k=3)

    return {
        "intent": decision["intent"],
        "needs_tool": False,
        "tool_name": "none",
        "answer": answer_data["answer"],
        "citations": answer_data["citations"],
        "reason": decision["reason"],
    }
