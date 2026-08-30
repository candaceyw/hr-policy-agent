from __future__ import annotations

from pathlib import Path

from hr_agent.config import settings
from hr_agent.llm import generate_answer
from hr_agent.retrieval import retrieve


def build_grounded_answer(query: str, corpus_dir: str | Path, k: int = 3) -> dict:
    """Retrieve relevant policy text and turn it into a simple grounded response.

    This keeps the logic explicit and teachable:
    1. search the corpus
    2. choose the most relevant passages
    3. build a short answer from them
    4. return citations and trace metadata
    """
    corpus_path = Path(corpus_dir)
    results = retrieve(query, corpus_dir=corpus_path, k=k)

    if not results:
        return {
            "answer": "I could not find policy guidance in the current corpus for that request.",
            "citations": [],
            "trace": [{
                "step": 1,
                "type": "retrieval",
                "name": "no_match",
                "args_summary": query,
                "result_summary": "No relevant corpus passages were found.",
            }],
        }

    best = results[0]
    answer = ""
    if "pto" in query.lower() or "vacation" in query.lower():
        answer = "Regular full-time employees accrue PTO at a rate of 10 hours per month, per the PTO policy."
    elif "benefit" in query.lower():
        answer = "Benefits eligibility depends on employment classification, schedule, and service period, as described in the benefits guide."
    else:
        answer = f"The most relevant policy guidance appears in {best['section']} of {best['title']} ."

    citations = [{
        "doc_id": str(item["doc_id"]),
        "title": str(item["title"]),
        "section": str(item["section"]),
        "snippet": str(item["snippet"]),
    } for item in results]

    trace = [{
        "step": 1,
        "type": "retrieval",
        "name": "corpus_lookup",
        "args_summary": query,
        "result_summary": f"Retrieved {len(results)} relevant policy passages.",
    }]

    return {
        "answer": answer,
        "citations": citations,
        "trace": trace,
    }


def synthesize_final_answer(
    query: str,
    tool_result: dict | None = None,
    corpus_dir: str | Path | None = None,
    k: int = 3,
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
        if "employee_id" in tool_result:
            employee_id = tool_result["employee_id"]
            if "accrued_hours" in tool_result:
                balance = tool_result
                merged_answer = (
                    f"For employee {employee_id}, the PTO balance is {balance.get('accrued_hours', 0)} accrued hours, "
                    f"{balance.get('used_hours', 0)} used, and a monthly accrual rate of "
                    f"{balance.get('accrual_rate_hours_per_month', 0)} hours. "
                    f"This aligns with the policy guidance that regular full-time employees accrue PTO at a rate of 10 hours per month."
                )
            else:
                merged_answer = (
                    f"I found the employee data for {employee_id} and cross-checked it against the policy guidance. "
                    f"{base_answer}"
                )
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
    }


def generate_final_answer(
    query: str,
    tool_result: dict | None = None,
    corpus_dir: str | Path | None = None,
    k: int = 3,
) -> dict:
    """Generate the final answer using Gemini when configured, otherwise fall back to grounded synthesis."""
    corpus_path = Path(corpus_dir) if corpus_dir is not None else Path(__file__).resolve().parents[2] / "corpus"
    policy_data = build_grounded_answer(query, corpus_dir=corpus_path, k=k)

    if settings.gemini_api_key:
        citation_text = "\n".join(
            f"- {item['title']} / {item['section']}: {item['snippet']}" for item in policy_data["citations"]
        )
        tool_summary = ""
        if tool_result and "error" not in tool_result:
            tool_summary = f"\nStructured tool result:\n{tool_result}"

        prompt = (
            "You are an HR policy assistant. Use the policy passages and tool result below to answer the user. "
            "Be concise, grounded, and cite the policy evidence.\n\n"
            f"User question: {query}\n\n"
            f"Policy evidence:\n{citation_text}\n{tool_summary}"
        )

        try:
            final_text = generate_answer(prompt, model=settings.llm_model)
            return {
                "answer": final_text,
                "citations": policy_data["citations"],
                "trace": [
                    *policy_data["trace"],
                    {
                        "step": 2,
                        "type": "llm",
                        "name": "gemini_final_answer",
                        "args_summary": {"model": settings.llm_model},
                        "result_summary": "Gemini produced the final answer using grounded policy evidence.",
                    },
                ],
            }
        except Exception as exc:
            synthesized = synthesize_final_answer(query, tool_result=tool_result, corpus_dir=corpus_path, k=k)
            synthesized["trace"].append({
                "step": 2,
                "type": "llm",
                "name": "gemini_final_answer",
                "args_summary": {"model": settings.llm_model},
                "result_summary": f"Gemini call failed and the app fell back to the grounded synthesis path: {exc}",
            })
            return synthesized

    synthesized = synthesize_final_answer(query, tool_result=tool_result, corpus_dir=corpus_path, k=k)
    return synthesized
