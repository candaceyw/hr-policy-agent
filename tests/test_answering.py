from pathlib import Path

import pytest

from hr_agent import answering
from hr_agent.answering import build_grounded_answer, generate_final_answer

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


def test_generate_final_answer_surfaces_llm_error(monkeypatch):
    def boom(prompt, *, model=None):
        raise RuntimeError("429 rate limit exceeded")

    monkeypatch.setattr(answering, "llm_available", lambda: True)
    monkeypatch.setattr(answering, "generate_answer", boom)

    result = generate_final_answer(
        "How much PTO do employees accrue per month?",
        corpus_dir=ROOT / "corpus",
        k=3,
    )

    assert result["llm_error"]
    assert "429 rate limit exceeded" in result["llm_error"]
    assert result["answer"]  # still answered via template fallback
    assert any("failed" in entry.get("result_summary", "").lower() for entry in result["trace"])


def _fake_vector_hits(score):
    return (
        [{"doc_id": "03-x", "title": "T", "section": "S", "snippet": "x", "score": score}],
        {"method": "vector", "note": None},
    )


def test_out_of_scope_query_is_redirected_without_an_llm_call(monkeypatch):
    from hr_agent.guardrails import SCOPE_REFUSAL

    monkeypatch.setattr(answering, "retrieve_passages", lambda *a, **k: _fake_vector_hits(0.40))
    monkeypatch.setattr(answering, "generate_answer", lambda *a, **k: pytest.fail("LLM was called"))

    result = generate_final_answer("who won the world cup in 2022", corpus_dir=ROOT / "corpus", k=3)
    assert result["answer"] == SCOPE_REFUSAL
    assert result["citations"] == []
    assert result["escalation"] is False


def test_thin_evidence_in_scope_sets_escalation(monkeypatch):
    monkeypatch.setattr(answering, "retrieve_passages", lambda *a, **k: _fake_vector_hits(0.57))
    result = generate_final_answer("a borderline HR question", corpus_dir=ROOT / "corpus", k=3)
    assert result["escalation"] is True


def test_generate_final_answer_reports_missing_credentials():
    # The autouse _offline_llm fixture forces llm_available() to False.
    result = generate_final_answer(
        "How much PTO do employees accrue per month?",
        corpus_dir=ROOT / "corpus",
        k=3,
    )

    assert result["llm_error"]
    assert "not configured" in result["llm_error"]
