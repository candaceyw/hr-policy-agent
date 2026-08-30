from __future__ import annotations

import logging
from pathlib import Path

from hr_agent.config import settings
from hr_agent.directory import get_employee_name
from hr_agent.guardrails import SCOPE_REFUSAL, is_in_scope, needs_escalation, top_score
from hr_agent.llm import generate_answer, llm_available, missing_credentials_message
from hr_agent.retrieval import retrieve_passages

logger = logging.getLogger(__name__)


def build_grounded_answer(query: str, corpus_dir: str | Path, k: int | None = None) -> dict:
    """Retrieve relevant policy text and turn it into a simple grounded response.

    This keeps the logic explicit and teachable:
    1. search the corpus
    2. choose the most relevant passages
    3. build a short answer from them
    4. return citations and trace metadata
    """
    corpus_path = Path(corpus_dir)
    k = k or settings.retrieval_k
    results, retrieval_meta = retrieve_passages(query, k=k, corpus_dir=corpus_path)
    method = retrieval_meta["method"]

    def _trace(name: str, summary: str) -> list[dict]:
        return [{
            "step": 1,
            "type": "retrieval",
            "name": name,
            "args_summary": query,
            "result_summary": summary,
        }]

    if not results:
        return {
            "answer": "I could not find policy guidance in the current corpus for that request.",
            "citations": [],
            "escalation": False,
            "in_scope": False,
            "trace": _trace(
                f"{method}_search",
                retrieval_meta["note"] or "No relevant corpus passages were found.",
            ),
        }

    # The similarity threshold is only meaningful for vector scores (0-1). The
    # keyword fallback's TF-IDF scores aren't calibrated, so we fail open there
    # and rely on the compose prompt to refuse.
    score = top_score(results)
    if method == "vector" and not is_in_scope(results):
        return {
            "answer": SCOPE_REFUSAL,
            "citations": [],
            "escalation": False,
            "in_scope": False,
            "trace": _trace(
                "scope_guardrail",
                f"out of scope: top similarity {score:.3f} < {settings.scope_threshold}",
            ),
        }

    escalation = method == "vector" and needs_escalation(results)
    citations = [{
        "doc_id": str(item["doc_id"]),
        "title": str(item["title"]),
        "section": str(item["section"]),
        "snippet": str(item["snippet"]),
    } for item in results]

    summary = f"{method} search: retrieved {len(results)} passages"
    if method == "vector":
        summary += f" (top {score:.3f})"
    if retrieval_meta["note"]:
        summary += f" -- {retrieval_meta['note']}"
    if escalation:
        summary += " -- thin corpus coverage, recommend confirming with HR"

    return {
        "answer": f"From {results[0]['title']} — {results[0]['section']}: {results[0]['snippet']}",
        "citations": citations,
        "escalation": escalation,
        "in_scope": True,
        "trace": _trace(f"{method}_search", summary),
    }


def synthesize_final_answer(
    query: str,
    tool_result: dict | None = None,
    corpus_dir: str | Path | None = None,
    k: int | None = None,
) -> dict:
    """Combine retrieved policy evidence with tool output into one final answer.

    This is the teachable bridge from retrieval-only to agentic assistant behavior:
    - retrieval provides policy grounding
    - tool result provides structured facts
    - synthesis merges both into a user-facing answer
    """
    corpus_path = Path(corpus_dir) if corpus_dir is not None else Path(__file__).resolve().parents[2] / "corpus"
    answer_data = build_grounded_answer(query, corpus_dir=corpus_path, k=k)

    base_answer = answer_data["answer"]
    citations = answer_data["citations"]
    trace = list(answer_data["trace"])

    if tool_result and "error" not in tool_result:
        if "ticket_id" in tool_result:
            merged_answer = (
                f"A mock HR ticket ({tool_result['ticket_id']}) was created for "
                f"{tool_result.get('employee_id', 'the employee')}. "
                f"Issue: {tool_result.get('issue', 'n/a')}. "
                f"Status: {tool_result.get('status', 'created')}. "
                f"{tool_result.get('note', '')}"
            ).strip()
        elif "draft" in tool_result:
            merged_answer = (
                f"Here is a mock HR email draft for "
                f"{tool_result.get('employee_id', 'the employee')} about "
                f"\"{tool_result.get('topic', 'the request')}\":\n\n{tool_result['draft']}"
            )
        elif "employee_id" in tool_result:
            employee_id = tool_result["employee_id"]
            name = get_employee_name(str(employee_id))
            who = f"{name} ({employee_id})" if name else f"Employee {employee_id}"
            if "accrued_hours" in tool_result:
                accrued = tool_result.get("accrued_hours", 0)
                used = tool_result.get("used_hours", 0)
                pending = tool_result.get("pending_hours", 0)
                rate = tool_result.get("accrual_rate_hours_per_month", 0)
                available = accrued - used - pending
                merged_answer = (
                    f"{who} has {available:g} hours of PTO available "
                    f"({accrued:g} accrued − {used:g} used − {pending:g} pending), "
                    f"accruing {rate:g} hours per month. "
                    f"Per the PTO and Vacation Policy, regular full-time employees accrue "
                    f"10 hours of PTO per month and may carry up to 40 hours into the next year."
                )
            elif "medical_plan" in tool_result:
                plan = str(tool_result.get("medical_plan", "none")).lower()
                plan_label = {
                    "ppo": "the PPO medical plan",
                    "hdhp": "the HDHP medical plan (paired with an HSA)",
                    "none": "no medical plan (coverage waived)",
                }.get(plan, f"the {plan} medical plan")
                extras = [k for k in ("dental", "vision") if tool_result.get(k)]
                extras_txt = f" They also have {' and '.join(extras)} coverage." if extras else ""
                status = tool_result.get("eligibility_status", "unknown")
                eff = tool_result.get("effective_date")
                eff_txt = f", effective {eff}" if eff else ""
                merged_answer = (
                    f"{who} is enrolled in {plan_label}.{extras_txt} "
                    f"Benefits eligibility status: {status}{eff_txt}. "
                    f"401(k) contribution: {tool_result.get('retirement_401k_pct', 0)}% of pay. "
                    f"FSA election: ${tool_result.get('fsa_annual', 0)}."
                )
            elif "title" in tool_result and "department" in tool_result:
                merged_answer = (
                    f"{who} is a {tool_result.get('title')} in {tool_result.get('department')}. "
                    f"Employment type: {str(tool_result.get('employment_type', 'n/a')).replace('_', ' ')}, "
                    f"{str(tool_result.get('exempt_status', 'n/a')).replace('_', '-')}. "
                    f"Work state: {tool_result.get('work_state', 'n/a')} "
                    f"(office {tool_result.get('office_location', 'n/a')}). "
                    f"Hire date: {tool_result.get('hire_date', 'n/a')}."
                )
            else:
                merged_answer = f"{who}: {tool_result}."
        elif "message" in tool_result:
            merged_answer = (
                f"{tool_result['message']} "
                f"I cross-checked this against the relevant policy guidance."
            )
        else:
            merged_answer = f"I checked the structured tool data and cross-referenced it with policy guidance. {base_answer}"
    else:
        merged_answer = base_answer

    trace.append({
        "step": 2,
        "type": "synthesis",
        "name": "merge_tool_and_policy",
        "args_summary": {
            "tool_result_present": tool_result is not None,
            "citations_count": len(citations),
        },
        "result_summary": "Combined structured tool data with retrieved policy citations into a final answer.",
    })

    return {
        "answer": merged_answer,
        "citations": citations,
        "trace": trace,
        "llm_error": None,
        "escalation": answer_data.get("escalation", False),
    }


def generate_final_answer(
    query: str,
    tool_result: dict | None = None,
    corpus_dir: str | Path | None = None,
    k: int | None = None,
) -> dict:
    """Generate the final answer with the configured LLM provider, otherwise fall back to grounded synthesis.

    Any fallback is reported, not hidden: the returned dict carries a non-null
    ``llm_error`` and a matching trace entry, and the exception is logged with a
    stack trace so it shows up in the server logs.
    """
    corpus_path = Path(corpus_dir) if corpus_dir is not None else Path(__file__).resolve().parents[2] / "corpus"
    policy_data = build_grounded_answer(query, corpus_dir=corpus_path, k=k)

    # Out-of-scope guardrail (policy questions only): return the redirect, no LLM call.
    if tool_result is None and not policy_data.get("in_scope", True):
        return {
            "answer": policy_data["answer"],
            "citations": [],
            "trace": policy_data["trace"],
            "llm_error": None,
            "escalation": False,
        }

    escalation = policy_data.get("escalation", False)

    if not llm_available():
        message = missing_credentials_message()
        logger.warning(
            "generate_final_answer: %s Set it in .env and restart the server for LLM-written answers.",
            message,
        )
        synthesized = synthesize_final_answer(query, tool_result=tool_result, corpus_dir=corpus_path, k=k)
        synthesized["llm_error"] = message
        return synthesized

    citation_text = "\n".join(
        f"- [{item['doc_id']}] {item['title']} / {item['section']}: {item['snippet']}"
        for item in policy_data["citations"]
    )
    tool_summary = ""
    if tool_result and "error" not in tool_result:
        tool_summary = f"\nStructured tool result:\n{tool_result}"

    prompt = (
        "You are an HR policy assistant for Northwind Robotics. Answer ONLY from the policy "
        "passages (and tool result) below. Structure the answer as two short parts:\n"
        '  "What the policy says": the grounded facts, each ending with its citation in '
        "brackets like [02-pto-and-vacation-policy].\n"
        '  "Suggested next steps": practical advice, kept clearly separate from stated policy.\n'
        "If the passages do not actually answer the question, say so plainly and recommend "
        "contacting HR -- do not guess.\n\n"
        f"User question: {query}\n\n"
        f"Policy evidence:\n{citation_text}\n{tool_summary}"
    )

    try:
        final_text = generate_answer(prompt, model=settings.llm_model)
    except Exception as exc:
        logger.exception("LLM final-answer call failed; falling back to template synthesis")
        synthesized = synthesize_final_answer(query, tool_result=tool_result, corpus_dir=corpus_path, k=k)
        synthesized["llm_error"] = f"{type(exc).__name__}: {exc}"
        synthesized["trace"].append({
            "step": len(synthesized["trace"]) + 1,
            "type": "llm",
            "name": "gemini_final_answer",
            "args_summary": {"model": settings.llm_model},
            "result_summary": (
                f"Gemini call failed ({type(exc).__name__}: {exc}); fell back to template synthesis."
            ),
        })
        return synthesized

    return {
        "answer": final_text,
        "citations": policy_data["citations"],
        "llm_error": None,
        "escalation": escalation,
        "trace": [
            *policy_data["trace"],
            {
                "step": len(policy_data["trace"]) + 1,
                "type": "llm",
                "name": "llm_final_answer",
                "args_summary": {"provider": settings.provider, "model": settings.llm_model},
                "result_summary": "LLM produced the final answer from grounded policy evidence.",
            },
        ],
    }
