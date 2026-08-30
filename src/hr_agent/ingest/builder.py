from __future__ import annotations

from pathlib import Path


def build_index(corpus_dir: str | Path, index_path: str | Path) -> Path:
    corpus_dir = Path(corpus_dir)
    index_path = Path(index_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)

    docs = sorted(corpus_dir.glob("*.md")) + sorted(corpus_dir.glob("*.txt"))
    if not docs:
        raise FileNotFoundError(f"No corpus documents found in {corpus_dir}")

    text_chunks: list[str] = []
    for doc in docs:
        content = doc.read_text(encoding="utf-8")
        text_chunks.append(f"# {doc.stem}\n{content}\n")

    combined = "\n---\n\n".join(text_chunks)
    index_path.write_text(combined, encoding="utf-8")
    return index_path
