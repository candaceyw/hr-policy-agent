from __future__ import annotations

from pathlib import Path
import re


def _split_into_sections(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    sections: list[tuple[str, str]] = []
    current_title = "Introduction"
    buffer: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            if buffer:
                sections.append((current_title, "\n".join(buffer).strip()))
            current_title = stripped.lstrip("# ").strip() or "Introduction"
            buffer = []
        else:
            buffer.append(line)

    if buffer:
        sections.append((current_title, "\n".join(buffer).strip()))

    return sections


def retrieve(query: str, corpus_dir: str | Path, k: int = 5) -> list[dict[str, str | float]]:
    """Return the most relevant policy passages for a query.

    This is a deliberately simple retrieval layer designed to teach the pattern.
    It scans the markdown corpus, scores each section by keyword overlaps, and
    returns the top matches with document id, section title, and snippet.
    """
    corpus_path = Path(corpus_dir)
    docs = sorted(corpus_path.glob("*.md"))
    if not docs:
        raise FileNotFoundError(f"No markdown corpus files found in {corpus_path}")

    query_terms = {term.lower() for term in re.findall(r"[a-zA-Z]+", query) if len(term) > 2}
    if not query_terms:
        query_terms = {query.lower()}

    scored: list[tuple[float, dict[str, str | float]]] = []

    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        sections = _split_into_sections(text)

        for section_title, section_text in sections:
            if not section_text:
                continue

            section_lower = section_text.lower()
            score = 0.0
            for term in query_terms:
                score += section_lower.count(term)

            if section_title.lower() not in {"introduction", "overview"}:
                score += 0.5

            if score <= 0:
                continue

            snippet = section_text.strip().replace("\n", " ")
            snippet = " ".join(snippet.split())
            if len(snippet) > 220:
                snippet = snippet[:217].rstrip() + "..."

            scored.append((score, {
                "doc_id": doc.stem,
                "title": doc.stem.replace("-", " ").title(),
                "section": section_title,
                "snippet": snippet,
                "score": float(score),
            }))

    scored.sort(key=lambda item: item[0], reverse=True)
    top_matches = [match for _, match in scored[:k]]

    return top_matches
