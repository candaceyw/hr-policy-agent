"""Write chunks + embeddings into a committable sqlite-vec index, and verify it.

The index is a single file (`data/index/index.sqlite`) plus a sidecar
`manifest.json`. `manifest.json` records what the index was built from so CI can
rebuild the *chunks* (deterministic, no embedding calls) and confirm they still
match -- see :func:`verify_index`.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import sqlite_vec

from hr_agent.config import settings
from hr_agent.ingest.chunker import PolicyChunk, chunk_corpus, chunks_content_hash

MANIFEST_NAME = "manifest.json"
# Fields that must match on --verify (built_at is informational and excluded).
_VERIFIED_FIELDS = (
    "chunk_count",
    "content_hash",
    "embedding_model",
    "embedding_dim",
    "chunk_size",
    "chunk_overlap",
)


def _connect(path: str | Path, *, read_only: bool = False) -> sqlite3.Connection:
    if read_only:
        conn = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(str(path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def _manifest_path(index_path: str | Path) -> Path:
    return Path(index_path).parent / MANIFEST_NAME


def build_index(
    chunks: list[PolicyChunk],
    vectors: list[list[float]],
    index_path: str | Path,
) -> dict:
    """Create the sqlite-vec index and its manifest. Returns the manifest dict."""
    if len(chunks) != len(vectors):
        raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")

    index_path = Path(index_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.unlink(missing_ok=True)

    conn = _connect(index_path)
    try:
        conn.execute(
            """
            CREATE TABLE chunks (
                rowid        INTEGER PRIMARY KEY,
                chunk_id     TEXT UNIQUE NOT NULL,
                doc_id       TEXT NOT NULL,
                doc_title    TEXT NOT NULL,
                section_path TEXT NOT NULL,
                chunk_index  INTEGER NOT NULL,
                source_format TEXT NOT NULL,
                text         TEXT NOT NULL
            )
            """
        )
        conn.execute(
            f"CREATE VIRTUAL TABLE vec_chunks USING vec0(embedding float[{settings.embedding_dim}])"
        )
        for i, (chunk, vector) in enumerate(zip(chunks, vectors), start=1):
            conn.execute(
                "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    i,
                    chunk.chunk_id,
                    chunk.doc_id,
                    chunk.doc_title,
                    chunk.section_path,
                    chunk.chunk_index,
                    chunk.source_format,
                    chunk.text,
                ),
            )
            conn.execute(
                "INSERT INTO vec_chunks(rowid, embedding) VALUES (?, ?)",
                (i, sqlite_vec.serialize_float32(vector)),
            )
        conn.commit()
    finally:
        conn.close()

    manifest = {
        "chunk_count": len(chunks),
        "content_hash": chunks_content_hash(chunks),
        "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    _manifest_path(index_path).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def load_manifest(index_path: str | Path) -> dict:
    return json.loads(_manifest_path(index_path).read_text(encoding="utf-8"))


def verify_index(corpus_dir: str | Path, index_path: str | Path) -> tuple[bool, list[str]]:
    """Re-chunk the corpus and confirm it still matches the committed manifest.

    Only chunking runs here -- no embedding calls -- so CI can verify offline.
    """
    manifest = load_manifest(index_path)
    fresh = chunk_corpus(
        corpus_dir, chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap
    )
    current = {
        "chunk_count": len(fresh),
        "content_hash": chunks_content_hash(fresh),
        "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
    }
    mismatches = [
        f"{field}: manifest={manifest.get(field)!r} current={current[field]!r}"
        for field in _VERIFIED_FIELDS
        if manifest.get(field) != current[field]
    ]
    return (not mismatches), mismatches
