from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """Shared state for the agent loop.

    ``messages`` accumulates the conversation (system + human + AI + tool
    messages); ``add_messages`` appends rather than overwrites. Everything else
    is derived output the web layer reads back.
    """

    query: str
    corpus_dir: str | None
    messages: Annotated[list[AnyMessage], add_messages]
    # operational trace only -- step/type/name/args_summary/result_summary/sources
    tool_trace: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    iterations: int
    nudges: int
    answer: str
    llm_error: str | None
    escalation: bool
    # confirmation gate (only used when the graph is built with confirm_gate=True)
    confirm: bool | None
    pending_action: dict[str, Any] | None
