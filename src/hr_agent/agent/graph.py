"""The agent loop: an LLM bound to MCP-discovered tools, cycling with a ToolNode.

    START -> agent -> (tool_calls?) -> tools -> agent -> ... -> compose -> END

The model chooses which discovered tools to call; ``ToolNode`` executes them
through the MCP client; results feed back as messages. The loop is bounded by
``settings.max_tool_iterations``. Only operational fields land in the trace --
never model reasoning.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from hr_agent.agent.gate import decide as gate_decide
from hr_agent.agent.state import AgentState
from hr_agent.config import settings
from hr_agent.directory import get_employee_name, resolve_employee
from hr_agent.guardrails import SCOPE_REFUSAL, top_score
from hr_agent.llm import chat_model
from hr_agent.retrieval import retrieve_passages

logger = logging.getLogger(__name__)

# Mock actions that must never run without an explicit user confirmation.
DESTRUCTIVE_TOOLS = {"create_mock_hr_ticket", "draft_hr_email"}
_ACTION_LABELS = {
    "create_mock_hr_ticket": "create a mock HR ticket",
    "draft_hr_email": "draft a mock HR email",
}

_AGENT_SYSTEM = (
    "You are an HR policy assistant for Northwind Robotics. You have tools to "
    "search the policy corpus and to look up synthetic employee data.\n"
    "Answer ONLY the question the user actually asked. Do not invent, assume, or "
    "expand it into a different request, and do not volunteer information they "
    "did not ask for.\n"
    "Tool discipline:\n"
    "- Ground every policy claim with a policy-search tool.\n"
    "- Call lookup_employee_profile for questions about a person's role, "
    "department, manager, location, or employment details. To name a referenced "
    "person (such as a manager id in a profile), call it again for that id.\n"
    "- Call check_pto_balance ONLY if the question is about time off or PTO.\n"
    "- Call lookup_benefits_status ONLY if the question is about benefits.\n"
    "- Call check_policy_compliance ONLY if the question asks whether something "
    "is allowed or compliant.\n"
    "When you have enough information, stop calling tools and write the answer.\n"
    "Answer format: at most ~120 words, in short prose or a few bullet points. "
    "Name the policy document for each policy fact (for example, 'the PTO and "
    "Vacation Policy'). Do NOT write a 'TL;DR', a summary heading, an email, a "
    "letter, or a sign-off, and do not offer to draft an email or open a ticket "
    "unless the user explicitly asked for one. If the tools do not answer the "
    "question, say so plainly and recommend contacting HR."
)


def _employee_hint(query: str, employee_id: str | None = None) -> str | None:
    """Pre-resolve the employee so the model doesn't have to parse it.

    Prefer a name/id in the query itself; fall back to ``employee_id`` (the
    gate's resolution, which includes the session's selected employee).
    """
    employee_id = resolve_employee(query) or employee_id
    if not employee_id:
        return None
    name = get_employee_name(employee_id)
    who = f"{name} ({employee_id})" if name else employee_id
    return f"Context: this request is about employee {who}; their employee id is {employee_id}."


# gpt-oss on Groq sometimes abandons a multi-tool task and replies with a generic
# greeting instead of an answer. One nudge back into the loop usually recovers it.
_MAX_NUDGES = 1
_FILLER_RE = re.compile(
    r"(?i)\b(sure thing|ready to help|ready whenever|let me know what|"
    r"how can i (?:help|assist)|here to assist|glad to help|"
    r"what .{0,25}question (?:do you|can i)|i'?m here to)\b"
)


def _looks_unfinished(state: AgentState) -> bool:
    """True when the loop is about to compose a non-answer.

    An empty final message is always unfinished. Greeting/filler ("I'm ready to
    help!") is unfinished even after a tool ran -- some models call a tool and
    then reply with filler instead of the answer -- but only when the message is
    short, so a real answer that happens to contain a stock phrase is left alone.
    """
    last = _last_ai(state)
    text = (last.content if last else "") or ""
    text = text if isinstance(text, str) else str(text)
    stripped = text.strip()
    if not stripped:
        return True
    return bool(_FILLER_RE.search(stripped)) and len(stripped) < 240

# Tool results we can turn into citations, plus how to read them.
_POLICY_TOOLS = {"search_policy_documents", "get_policy_section", "list_policy_documents"}
_MAX_ARGS_SUMMARY = 200


def _summarize_args(args: dict[str, Any]) -> str:
    text = json.dumps(args, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= _MAX_ARGS_SUMMARY else text[:_MAX_ARGS_SUMMARY] + "…"


def _parse_tool_payload(message: ToolMessage) -> Any:
    """Best-effort decode of a ToolMessage into a Python object.

    MCP-adapter results arrive either as a JSON string or as a list of content
    blocks (``[{"type": "text", "text": "<json>"}]``).
    """
    content: Any = message.content
    if isinstance(content, list):
        text = "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
        content = text or content
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return content
    return content


def _citations_from_payload(payload: Any) -> list[dict[str, str]]:
    """Pull ``{doc_id,title,section,snippet}`` rows out of a policy tool result."""
    rows: list[dict[str, str]] = []
    candidates: list[Any] = []
    if isinstance(payload, dict):
        if isinstance(payload.get("results"), list):
            candidates = payload["results"]
        elif "doc_id" in payload:
            candidates = [payload]
    for item in candidates:
        if not isinstance(item, dict) or "doc_id" not in item:
            continue
        rows.append(
            {
                "doc_id": str(item.get("doc_id", "")),
                "title": str(item.get("title", item.get("doc_id", ""))),
                "section": str(item.get("section", "")),
                "snippet": str(item.get("snippet", item.get("content", "")))[:400],
            }
        )
    return rows


def _dedupe_citations(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for row in rows:
        key = (row["doc_id"], row["section"])
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out


# Every policy-tool result row is collected as a candidate citation, so the agent
# over-cites (eval: recall 0.86 >> precision 0.55). Keep only the documents the
# composed answer actually names -- the model reliably writes prose names like
# "the PTO and Vacation Policy", which map onto the doc-id stem. Fall back to the
# first few (retrieval order) when the answer names none, so a real answer never
# loses all its citations.
_CITATION_CAP = 4
_CITATION_STOPWORDS = frozenset(
    {"and", "of", "the", "to", "for", "a", "an", "policy", "guide", "overview",
     "standard", "procedure", "northwind", "robotics"}
)


def _doc_id_significant_words(doc_id: str) -> list[str]:
    """Content words of a doc-id stem: ``05-out-of-state-and-international-remote-work``
    -> ``["out", "state", "international", "remote", "work"]``."""
    words = [w for w in re.split(r"[-_\s]+", doc_id.lower()) if w and not w.isdigit()]
    return [w for w in words if w not in _CITATION_STOPWORDS]


def _answer_names_doc(doc_id: str, answer_norm: str) -> bool:
    """True when ``answer_norm`` (lower-cased, hyphens -> spaces) names this doc."""
    full_phrase = " ".join(
        w for w in re.split(r"[-_\s]+", doc_id.lower()) if w and not w.isdigit()
    )
    if full_phrase and full_phrase in answer_norm:
        return True
    words = _doc_id_significant_words(doc_id)
    if not words:
        return False
    hits = sum(1 for w in words if re.search(rf"\b{re.escape(w)}\b", answer_norm))
    need = len(words) if len(words) <= 2 else max(2, len(words) - 1)
    return hits >= need


def _select_citations(rows: list[dict[str, str]], answer: str) -> list[dict[str, str]]:
    rows = _dedupe_citations(rows)
    if not rows:
        return []
    answer_norm = re.sub(r"[-_]+", " ", (answer or "").lower())
    named = [r for r in rows if _answer_names_doc(r["doc_id"], answer_norm)]
    if named:
        # a little slack over the cap when the answer genuinely cites many docs
        return named[: _CITATION_CAP + 2]
    return rows[:_CITATION_CAP]


def _last_ai(state: AgentState) -> AIMessage | None:
    return next(
        (m for m in reversed(state.get("messages") or []) if isinstance(m, AIMessage)),
        None,
    )


def _destructive_calls(message: Any) -> list[dict]:
    if not isinstance(message, AIMessage):
        return []
    return [tc for tc in message.tool_calls if tc.get("name") in DESTRUCTIVE_TOOLS]


def _describe_action(call: dict, query: str) -> str:
    label = _ACTION_LABELS.get(call.get("name", ""), f"run {call.get('name', 'a tool')}")
    employee_id = call.get("args", {}).get("employee_id") or resolve_employee(query) or "E-1001"
    return f"{label} for {employee_id}"


def build_agent_graph(
    tools: list[BaseTool],
    model: Any | None = None,
    *,
    confirm_gate: bool = False,
    gate: bool = False,
):
    """Compile the agent loop over ``tools``.

    ``model`` is injectable for offline tests; when ``None`` it is resolved from
    config on first use (so importing this module never needs credentials).
    ``confirm_gate=True`` adds a human-in-the-loop pause before any tool in
    :data:`DESTRUCTIVE_TOOLS`: the run stops with ``pending_action`` unless
    ``state["confirm"]`` is ``True``; ``False`` records a decline.
    ``gate=True`` puts a deterministic ``classify_intent`` node in front of the
    loop that can short-circuit to ``clarify`` (missing/unknown employee, or an
    ambiguous request) or ``guardrail_scope`` (out-of-corpus policy question).
    """
    tool_node = ToolNode(tools)
    _model_box: dict[str, Any] = {"model": model}

    def _bound_model():
        if _model_box["model"] is None:
            _model_box["model"] = chat_model()
        m = _model_box["model"]
        return m.bind_tools(tools) if tools else m

    async def agent_node(state: AgentState) -> dict:
        messages = list(state.get("messages") or [])
        if not messages:
            system = _AGENT_SYSTEM
            hint = _employee_hint(state["query"], state.get("employee_id"))
            if hint:
                system = f"{system}\n{hint}"
            history = list(state.get("history") or [])
            messages = [SystemMessage(system), *history, HumanMessage(state["query"])]
        try:
            response = await _bound_model().ainvoke(messages)
            return {"messages": [response], "llm_error": None}
        except Exception as exc:
            logger.exception("agent model call failed")
            return {
                "messages": [AIMessage(content="")],
                "llm_error": f"{type(exc).__name__}: {exc}",
            }

    async def tools_node(state: AgentState) -> dict:
        # MCP-adapter tools are async-only, so the loop must run under ainvoke.
        result = await tool_node.ainvoke(state)
        new_messages: list[Any] = result["messages"] if isinstance(result, dict) else result

        step = len(state.get("tool_trace") or [])
        trace = list(state.get("tool_trace") or [])
        citations = list(state.get("citations") or [])

        last_ai = next(
            (m for m in reversed(state.get("messages") or []) if isinstance(m, AIMessage)),
            None,
        )
        calls_by_id = {c.get("id"): c for c in (last_ai.tool_calls if last_ai else [])}

        for msg in new_messages:
            if not isinstance(msg, ToolMessage):
                continue
            step += 1
            call = calls_by_id.get(msg.tool_call_id, {})
            payload = _parse_tool_payload(msg)
            is_error = isinstance(payload, dict) and "error" in payload
            trace.append(
                {
                    "step": step,
                    "type": "tool_call",
                    "name": msg.name or call.get("name", "unknown"),
                    "args_summary": _summarize_args(call.get("args", {})),
                    "result_summary": (
                        f"error: {payload['error']}"
                        if is_error
                        else "ok"
                    ),
                }
            )
            if (msg.name in _POLICY_TOOLS) and not is_error:
                citations.extend(_citations_from_payload(payload))

        return {
            "messages": new_messages,
            "tool_trace": trace,
            "citations": _dedupe_citations(citations),
            "iterations": state.get("iterations", 0) + 1,
        }

    def classify_node(state: AgentState) -> dict:
        """Deterministic pre-agent gate. No LLM call; may short-circuit the run."""
        query = state["query"]
        results: list[dict] = []
        method: str | None = None
        try:
            results, meta = retrieve_passages(query, corpus_dir=state.get("corpus_dir"))
            method = meta.get("method")
        except Exception as exc:  # noqa: BLE001 - the gate must never crash the request
            logger.warning("classify_node retrieval failed: %s", exc)

        decision = gate_decide(
            query,
            employee_id_hint=state.get("employee_id"),
            retrieval_results=results,
            retrieval_method=method,
            has_history=bool(state.get("history")),
        )
        trace = list(state.get("tool_trace") or [])
        trace.append(
            {
                "step": len(trace) + 1,
                "type": "classify",
                "name": "classify_intent",
                "args_summary": _summarize_args({"query": query}),
                "result_summary": f"intent={decision.intent}; route={decision.route}",
            }
        )
        return {
            "intent": decision.intent,
            "gate_route": decision.route,
            "gate_message": decision.message,
            "employee_id": decision.employee_id,
            "scope_score": top_score(results),
            "tool_trace": trace,
        }

    def clarify_node(state: AgentState) -> dict:
        """Ask exactly one clarifying question and stop; nothing else runs."""
        trace = list(state.get("tool_trace") or [])
        trace.append(
            {
                "step": len(trace) + 1,
                "type": "clarify",
                "name": "request_clarification",
                "result_summary": "Asked one clarifying question; no tools called.",
            }
        )
        return {
            "answer": state.get("gate_message") or "Could you give me a bit more detail?",
            "citations": [],
            "tool_trace": trace,
            "escalation": False,
            "pending_action": None,
            "intent": "clarify",
        }

    def guardrail_scope_node(state: AgentState) -> dict:
        """Out-of-corpus policy question: fixed redirect, no LLM call."""
        score = float(state.get("scope_score", 0.0))
        if score >= settings.scope_threshold:
            # routed here by the gate's off-topic keyword filter, not the score
            summary = (
                f"off-topic query (keyword filter); redirected out of scope "
                f"despite top similarity {score:.3f}"
            )
        else:
            summary = (
                f"out of scope: top similarity {score:.3f} < {settings.scope_threshold}"
            )
        trace = list(state.get("tool_trace") or [])
        trace.append(
            {
                "step": len(trace) + 1,
                "type": "guardrail",
                "name": "scope_refusal",
                "result_summary": summary,
            }
        )
        return {
            "answer": SCOPE_REFUSAL,
            "citations": [],
            "tool_trace": trace,
            "escalation": False,
            "pending_action": None,
            "intent": "out_of_scope",
        }

    def compose_node(state: AgentState) -> dict:
        messages = state.get("messages") or []
        last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        answer = (last_ai.content if last_ai else "") or ""
        if not isinstance(answer, str):
            answer = str(answer)
        answer = answer.strip()

        if not answer:
            if state.get("llm_error"):
                answer = (
                    "I could not reach the language model to complete this answer. "
                    "Please try again shortly or contact HR directly."
                )
            else:
                answer = (
                    "I gathered information but could not finish a complete answer. "
                    "Please contact HR for help with this request."
                )

        trace = list(state.get("tool_trace") or [])
        tool_calls = sum(1 for e in trace if e.get("type") == "tool_call")
        trace.append(
            {
                "step": len(trace) + 1,
                "type": "compose",
                "name": "compose_answer",
                "result_summary": f"Final answer composed from {tool_calls} tool call(s).",
            }
        )
        return {
            "answer": answer,
            "citations": _select_citations(list(state.get("citations") or []), answer),
            "tool_trace": trace,
            "escalation": bool(state.get("escalation", False)),
        }

    def confirm_gate_node(state: AgentState) -> dict:
        """Stop before a mock action; surface it for the user to confirm."""
        call = _destructive_calls(_last_ai(state))[0]
        description = _describe_action(call, state["query"])
        args_summary = _summarize_args(call.get("args", {}))
        trace = list(state.get("tool_trace") or [])
        trace.append(
            {
                "step": len(trace) + 1,
                "type": "confirmation",
                "name": "confirmation_required",
                "args_summary": args_summary,
                "result_summary": f"Waiting for user confirmation before calling {call['name']}.",
            }
        )
        return {
            "pending_action": {
                "tool": call["name"],
                "args_summary": args_summary,
                "description": description[0].upper() + description[1:],
            },
            "answer": (
                f"This would {description}. It is a mock action and nothing has run yet — "
                "confirm to proceed or decline to cancel."
            ),
            "tool_trace": trace,
            "citations": _select_citations(list(state.get("citations") or []), state.get("answer") or ""),
        }

    def declined_node(state: AgentState) -> dict:
        """Record that the user declined the mock action; run nothing."""
        last_ai = _last_ai(state)
        calls = last_ai.tool_calls if last_ai else []
        description = _describe_action(_destructive_calls(last_ai)[0], state["query"])
        trace = list(state.get("tool_trace") or [])
        trace.append(
            {
                "step": len(trace) + 1,
                "type": "confirmation",
                "name": "confirmation_declined",
                "args_summary": _summarize_args(_destructive_calls(last_ai)[0].get("args", {})),
                "result_summary": "User declined the mock action; nothing was called.",
            }
        )
        # Close out every pending tool_call so the message history stays valid.
        tool_msgs = [
            ToolMessage(
                content="The user declined this action; it was not performed.",
                tool_call_id=tc["id"],
                name=tc["name"],
            )
            for tc in calls
        ]
        return {
            "messages": tool_msgs,
            "pending_action": None,
            "answer": (
                f"Okay, I did not {description}. Nothing was executed. "
                "Ask again with a confirmation if you want me to proceed."
            ),
            "tool_trace": trace,
            "citations": _select_citations(list(state.get("citations") or []), state.get("answer") or ""),
        }

    def nudge_node(state: AgentState) -> dict:
        """Push an abandoned task back into the loop once (see _looks_unfinished)."""
        return {
            "messages": [
                HumanMessage(
                    "You have not answered my question yet. Use the available tools "
                    "to gather what you need, then give me the complete answer."
                )
            ],
            "nudges": state.get("nudges", 0) + 1,
        }

    def route(state: AgentState) -> str:
        last = state["messages"][-1] if state.get("messages") else None
        if not (isinstance(last, AIMessage) and last.tool_calls):
            if _looks_unfinished(state) and state.get("nudges", 0) < _MAX_NUDGES:
                return "nudge"
            return "compose"
        if confirm_gate and _destructive_calls(last):
            decision = state.get("confirm")
            if decision is True:
                return "tools"
            if decision is False:
                return "declined"
            return "confirm_gate"
        if state.get("iterations", 0) >= settings.max_tool_iterations:
            return "compose"
        return "tools"

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("compose", compose_node)
    graph.add_node("nudge", nudge_node)

    targets = {"tools": "tools", "compose": "compose", "nudge": "nudge"}
    if confirm_gate:
        graph.add_node("confirm_gate", confirm_gate_node)
        graph.add_node("declined", declined_node)
        targets |= {"confirm_gate": "confirm_gate", "declined": "declined"}

    if gate:
        graph.add_node("classify", classify_node)
        graph.add_node("clarify", clarify_node)
        graph.add_node("guardrail_scope", guardrail_scope_node)
        graph.add_edge(START, "classify")
        graph.add_conditional_edges(
            "classify",
            lambda s: s.get("gate_route", "agent"),
            {"agent": "agent", "clarify": "clarify", "scope": "guardrail_scope"},
        )
        graph.add_edge("clarify", END)
        graph.add_edge("guardrail_scope", END)
    else:
        graph.add_edge(START, "agent")

    graph.add_conditional_edges("agent", route, targets)
    graph.add_edge("tools", "agent")
    graph.add_edge("nudge", "agent")
    graph.add_edge("compose", END)
    if confirm_gate:
        graph.add_edge("confirm_gate", END)
        graph.add_edge("declined", END)
    return graph.compile()


async def arun_agent(query: str, tools: list[BaseTool], *, model: Any | None = None) -> dict:
    """Run the agent loop once (async) and return the composed result.

    Async because ``langchain-mcp-adapters`` tools are coroutine-only; ``ToolNode``
    must ``await`` them.
    """
    graph = build_agent_graph(tools, model=model)
    final = await graph.ainvoke(
        {"query": query, "messages": [], "tool_trace": [], "citations": [], "iterations": 0}
    )
    return {
        "answer": final.get("answer", ""),
        "citations": final.get("citations", []),
        "trace": final.get("tool_trace", []),
        "llm_error": final.get("llm_error"),
        "escalation": bool(final.get("escalation", False)),
        "iterations": final.get("iterations", 0),
    }


def run_agent(query: str, tools: list[BaseTool], *, model: Any | None = None) -> dict:
    """Sync wrapper over :func:`arun_agent` for scripts and plain ``def`` routes.

    Do not call from inside a running event loop; use :func:`arun_agent` there.
    """
    return asyncio.run(arun_agent(query, tools, model=model))


def _result_dict(final: dict) -> dict:
    return {
        "answer": final.get("answer", ""),
        "citations": final.get("citations", []),
        "trace": final.get("tool_trace", []),
        "llm_error": final.get("llm_error"),
        "escalation": bool(final.get("escalation", False)),
        "pending_action": final.get("pending_action"),
        "iterations": final.get("iterations", 0),
        "intent": final.get("intent", ""),
        "employee_id": final.get("employee_id"),
    }


async def arun_workflow(
    query: str,
    tools: list[BaseTool],
    *,
    confirm: bool | None = None,
    model: Any | None = None,
    employee_id: str | None = None,
    corpus_dir: str | None = None,
    history: list[Any] | None = None,
) -> dict:
    """Deterministic gate + agent loop + destructive-action confirmation gate.

    ``confirm`` gates the mock actions: ``None`` returns ``pending_action`` and
    runs nothing, ``False`` records a decline, ``True`` executes the action.
    ``employee_id`` is the session id from the request; the gate uses it when the
    query names no one. ``history`` is prior (user, assistant) messages for this
    session; it seeds the first model call and relaxes the scope guardrail (a
    follow-up in an open HR conversation is almost certainly in scope).
    """
    graph = build_agent_graph(tools, model=model, confirm_gate=True, gate=True)
    final = await graph.ainvoke(
        {
            "query": query,
            "messages": [],
            "history": history or [],
            "tool_trace": [],
            "citations": [],
            "iterations": 0,
            "confirm": confirm,
            "pending_action": None,
            "employee_id": employee_id,
            "corpus_dir": corpus_dir,
        }
    )
    return _result_dict(final)
