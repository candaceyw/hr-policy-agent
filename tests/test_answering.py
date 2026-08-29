from pathlib import Path

from hr_agent.answering import build_grounded_answer


ROOT = Path(__file__).resolve().parents[1]


def test_build_grounded_answer_returns_answer_and_citations():
    result = build_grounded_answer(
        "How much PTO do employees accrue per month?",
        corpus_dir=ROOT / "corpus",
        k=3,
    )

    assert result["answer"]
    assert result["citations"]
    assert any(item["doc_id"].startswith("02-") for item in result["citations"])
    assert result["trace"]
