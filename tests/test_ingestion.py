from pathlib import Path

from hr_agent.ingest.builder import build_index


def test_build_index_from_corpus(tmp_path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "a.md").write_text("# PTO Policy\n\nAll employees accrue 10 hours per month.\n", encoding="utf-8")
    (corpus_dir / "b.md").write_text("# Benefits\n\nFull-time employees receive health benefits.\n", encoding="utf-8")

    index_path = tmp_path / "index.sqlite"
    build_index(corpus_dir=corpus_dir, index_path=index_path)

    assert index_path.exists()
    assert index_path.stat().st_size > 0

    rows = index_path.read_bytes()
    assert b"PTO" in rows
    assert b"Benefits" in rows
