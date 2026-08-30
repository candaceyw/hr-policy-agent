"""Request orchestration: drive the MCP agent loop, or degrade to RAG-only.

The agent loop (``hr_agent.agent.graph``) is the real path: an LLM binds the
MCP-discovered tools and chooses which to call, with a confirmation gate before
mock actions. When there are no tools (MCP server unreachable) or no usable LLM,
this module falls back to grounded retrieval synthesis so the app still answers.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool

from hr_agent.agent.graph import DESTRUCTIVE_TOOLS, arun_workflow
from hr_agent.answering import generate_final_answer
from hr_agent.llm import llm_available
from hr_agent.mcp_client import discovery

__all__ = ["DESTRUCTIVE_TOOLS", "arun_chat", "run_workflow"]

logger = logging.getLogger(__name__)


def _rag_only(query: str, corpus_dir: str | None, *, reason: str) -> dict:
    """Answer from retrieval alone (no tools). Used when MCP/LLM is unavailable."""
    data = generate_final_answer(query, tool_result=None, corpus_dir=corpus_dir)
    trace = list(data.get("trace") or [])
    trace.append(
        {
            "step": len(trace) + 1,
            "type": "degradation",
            "name": "rag_only",
            "result_summary": reason,
        }
    )
    return {
        "answer": data.get("answer", ""),
        "citations": data.get("citations", []),
        "trace": trace,
        "escalation": bool(data.get("escalation", False)),
        "pending_action": None,
        "llm_error": data.get("llm_error"),
    }


async def arun_chat(
    query: str,
    tools: list[BaseTool] | None,
    *,
    confirm: bool | None = None,
    corpus_dir: str | None = None,
    model: Any | None = None,
) -> dict:
    """Async entry the web layer awaits. Chooses the agent loop or the fallback."""
    if not tools:
        return _rag_only(query, corpus_dir, reason="MCP tools unavailable; answered from retrieval only.")
    if model is None and not llm_available():
        return _rag_only(query, corpus_dir, reason="No LLM credentials; answered from retrieval only.")
    return await arun_workflow(query, tools, confirm=confirm, model=model)


def run_workflow(
    query: str,
    tools: list[BaseTool] | None = None,
    *,
    corpus_dir: str | None = None,
    confirm: bool | None = None,
    model: Any | None = None,
) -> dict:
    """Sync wrapper for scripts and tests. Discovers tools if none are passed.

    Do not call from inside a running event loop; the web layer awaits
    :func:`arun_chat` directly.
    """
    if tools is None:
        try:
            tools = discovery.get_tools()
        except Exception:
            logger.exception("MCP discovery failed in run_workflow; degrading to RAG-only")
            tools = []
    if corpus_dir is None:
        corpus_dir = str(Path(__file__).resolve().parents[2] / "corpus")
    return asyncio.run(
        arun_chat(query, tools, confirm=confirm, corpus_dir=corpus_dir, model=model)
    )
