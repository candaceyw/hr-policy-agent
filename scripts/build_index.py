"""Build (or verify) the committed vector index.

    python scripts/build_index.py            # chunk -> embed -> write data/index/
    python scripts/build_index.py --verify   # re-chunk and check it matches manifest.json (offline)

Run from the repo root.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from hr_agent.config import settings
from hr_agent.ingest.chunker import chunk_corpus
from hr_agent.ingest.indexer import build_index, verify_index
from hr_agent.llm import embed, embedding_available
from hr_agent.vector_store import DEFAULT_INDEX_PATH

CORPUS_DIR = Path(__file__).resolve().parents[1] / "corpus"


def _build() -> int:
    if not embedding_available():
        print("ERROR: GEMINI_API_KEY is not set (required to embed the corpus).", file=sys.stderr)
        return 1

    print(f"Chunking {CORPUS_DIR} at chunk_size={settings.chunk_size} overlap={settings.chunk_overlap}")
    chunks = chunk_corpus(
        CORPUS_DIR, chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap
    )
    print(f"  {len(chunks)} chunks")

    print(f"Embedding with {settings.embedding_model} ({settings.embedding_dim}-dim) ...")
    started = time.monotonic()
    vectors = embed([c.text for c in chunks], task_type="retrieval_document")
    print(f"  {len(vectors)} vectors in {time.monotonic() - started:.1f}s")

    manifest = build_index(chunks, vectors, DEFAULT_INDEX_PATH)
    print(f"Wrote {DEFAULT_INDEX_PATH}")
    print(f"  chunk_count={manifest['chunk_count']} content_hash={manifest['content_hash'][:16]}...")
    return 0


def _verify() -> int:
    ok, mismatches = verify_index(CORPUS_DIR, DEFAULT_INDEX_PATH)
    if ok:
        print("Index verify: OK (chunks match manifest.json)")
        return 0
    print("Index verify: MISMATCH", file=sys.stderr)
    for line in mismatches:
        print(f"  {line}", file=sys.stderr)
    print("  -> run `python scripts/build_index.py` to rebuild", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="check the index without rebuilding")
    args = parser.parse_args()
    return _verify() if args.verify else _build()


if __name__ == "__main__":
    raise SystemExit(main())
