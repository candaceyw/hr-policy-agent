"""End-to-end check of the real ingest pipeline: chunk_corpus -> indexer.build_index.

The chunking rules themselves are covered in test_chunker.py; this exercises the
sqlite-vec index writer and its manifest, which nothing else touches.
"""

import sqlite3

from hr_agent.config import settings
from hr_agent.ingest.chunker import chunk_corpus, chunks_content_hash
from hr_agent.ingest.indexer import build_index, load_manifest


def test_build_index_writes_chunks_and_manifest(tmp_path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "a.md").write_text(
        "# PTO Policy\n\n## Accrual\n\nAll employees accrue 10 hours of PTO per month.\n",
        encoding="utf-8",
    )
    (corpus_dir / "b.md").write_text(
        "# Benefits\n\n## Eligibility\n\nFull-time employees receive health benefits.\n",
        encoding="utf-8",
    )

    chunks = chunk_corpus(
        corpus_dir, chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap
    )
    assert chunks, "the tiny corpus should still produce at least one chunk"
    # Deterministic stand-in vectors of the configured width -- no network.
    vectors = [[0.0] * settings.embedding_dim for _ in chunks]

    index_path = tmp_path / "index" / "index.sqlite"
    manifest = build_index(chunks, vectors, index_path)

    assert index_path.exists() and index_path.stat().st_size > 0
    assert manifest["chunk_count"] == len(chunks)
    assert manifest["content_hash"] == chunks_content_hash(chunks)
    assert load_manifest(index_path) == manifest

    conn = sqlite3.connect(index_path)
    try:
        rows = conn.execute("SELECT doc_id, text FROM chunks").fetchall()
    finally:
        conn.close()
    assert len(rows) == len(chunks)
    assert {doc_id for doc_id, _ in rows} == {"a", "b"}
    assert any("PTO" in text for _, text in rows)


def test_build_index_rejects_mismatched_vector_count(tmp_path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "a.md").write_text("# Doc\n\n## S\n\nA short policy sentence.\n", encoding="utf-8")
    chunks = chunk_corpus(
        corpus_dir, chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap
    )

    try:
        build_index(chunks, vectors=[], index_path=tmp_path / "index.sqlite")
    except ValueError as exc:
        assert "chunks but" in str(exc)
    else:  # pragma: no cover - the call must raise
        raise AssertionError("build_index should reject a chunk/vector length mismatch")
