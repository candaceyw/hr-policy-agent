"""Read-side of the vector index: nearest-neighbour search over policy chunks."""

from __future__ import annotations

from pathlib import Path

import sqlite_vec

from hr_agent.config import settings
from hr_agent.ingest.indexer import _connect

DEFAULT_INDEX_PATH = Path(__file__).resolve().parents[2] / "data" / "index" / "index.sqlite"

# sqlite-vec KNN needs its own `k = ?` constraint; join metadata to it via a CTE.
_SEARCH_SQL = """
    WITH knn AS (
        SELECT rowid, distance
        FROM vec_chunks
        WHERE embedding MATCH ? AND k = ?
    )
    SELECT c.chunk_id, c.doc_id, c.doc_title, c.section_path, c.source_format, c.text,
           knn.distance
    FROM knn
    JOIN chunks c ON c.rowid = knn.rowid
    ORDER BY knn.distance
"""


def index_exists(index_path: str | Path = DEFAULT_INDEX_PATH) -> bool:
    return Path(index_path).is_file()


def search(
    query_vector: list[float],
    k: int | None = None,
    index_path: str | Path = DEFAULT_INDEX_PATH,
) -> list[dict[str, str | float]]:
    """Return the ``k`` nearest chunks to ``query_vector`` from the committed index.

    Result shape matches the keyword retriever's, so downstream code doesn't care
    which retriever produced it: doc_id, title, section, snippet, source_format, score.
    """
    k = k or settings.retrieval_k
    conn = _connect(index_path, read_only=True)
    try:
        rows = conn.execute(
            _SEARCH_SQL, (sqlite_vec.serialize_float32(query_vector), k)
        ).fetchall()
    finally:
        conn.close()

    results: list[dict[str, str | float]] = []
    for chunk_id, doc_id, doc_title, section_path, source_format, text, distance in rows:
        section = section_path.split(" > ", 1)[-1]
        snippet = " ".join(text.split())
        if len(snippet) > 220:
            snippet = snippet[:217].rstrip() + "..."
        results.append({
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "title": doc_title,
            "section": section,
            "snippet": snippet,
            "source_format": source_format,
            # L2 distance on unit vectors -> smaller is closer; expose a similarity.
            "score": round(1.0 - (float(distance) ** 2) / 2.0, 4),
        })
    return results
