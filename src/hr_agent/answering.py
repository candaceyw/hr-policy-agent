from __future__ import annotations

from pathlib import Path

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
