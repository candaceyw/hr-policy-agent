from pathlib import Path

from hr_agent.retrieval import retrieve


ROOT = Path(__file__).resolve().parents[1]


def test_retrieve_returns_relevant_pto_policy():
    results = retrieve(
        "How much PTO do employees accrue per month?",
        corpus_dir=ROOT / "corpus",
        k=3,
    )

    assert results
    assert any(result["doc_id"].startswith("02-") for result in results)
    assert all(result["snippet"] for result in results)
    assert any("PTO" in result["title"] or "PTO" in result["snippet"] for result in results)
