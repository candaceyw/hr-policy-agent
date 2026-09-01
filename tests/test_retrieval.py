from pathlib import Path

import pytest

from hr_agent import retrieval
from hr_agent.llm import embedding_available
from hr_agent.retrieval import retrieve, retrieve_passages

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "corpus"


def test_retrieve_returns_relevant_pto_policy():
    results = retrieve(
        "How much PTO do employees accrue per month?",
        corpus_dir=CORPUS,
        k=3,
    )

    assert results
    assert any(result["doc_id"].startswith("02-") for result in results)
    assert all(result["snippet"] for result in results)
    assert any("PTO" in result["title"] or "PTO" in result["snippet"] for result in results)


def test_retrieve_passages_falls_back_to_keyword_without_embedding_key():
    # The autouse _offline_llm fixture forces embedding_available() -> False.
    results, meta = retrieve_passages("how much PTO per month", k=3, corpus_dir=CORPUS)
    assert meta["method"] == "keyword"
    assert "GEMINI_API_KEY" in meta["note"]
    assert results


def test_retrieve_passages_falls_back_when_index_is_missing(monkeypatch):
    monkeypatch.setattr("hr_agent.vector_store.index_exists", lambda *a, **k: False)
    results, meta = retrieve_passages("holiday pay rules", k=3, corpus_dir=CORPUS)
    assert meta["method"] == "keyword"
    assert "build_index" in meta["note"]
    assert results


@pytest.mark.skipif(not embedding_available(), reason="GEMINI_API_KEY not set; live vector test skipped")
def test_retrieve_passages_uses_vector_index_when_available(monkeypatch):
    monkeypatch.setattr(retrieval, "embedding_available", lambda: True)
    results, meta = retrieve_passages(
        "how much paid time off do I get each month", k=3, corpus_dir=CORPUS
    )
    assert meta["method"] == "vector"
    assert meta["note"] is None
    assert results[0]["doc_id"].startswith("02-")  # PTO policy, despite no shared words


@pytest.mark.skipif(not embedding_available(), reason="GEMINI_API_KEY not set; live vector test skipped")
def test_complex_question_retrieves_across_multiple_policy_documents(monkeypatch):
    monkeypatch.setattr(retrieval, "embedding_available", lambda: True)
    results, meta = retrieve_passages(
        "I want to work from Ireland for six weeks. What approvals do I need "
        "and what applies to my laptop and data access?",
        k=5,
        corpus_dir=CORPUS,
    )
    assert meta["method"] == "vector"
    assert len({r["doc_id"] for r in results}) >= 2
