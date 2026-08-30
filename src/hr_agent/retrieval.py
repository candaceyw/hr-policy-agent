from __future__ import annotations

import logging
import math
import re
from pathlib import Path

from hr_agent.config import settings
from hr_agent.llm import embed, embedding_available

logger = logging.getLogger(__name__)

CORPUS_GLOBS = ("*.md", "*.txt", "*.html", "*.pdf")
DEFAULT_CORPUS_DIR = Path(__file__).resolve().parents[2] / "corpus"

# Common English words carry no retrieval signal.
_STOPWORDS = frozenset({
    "a", "about", "an", "and", "any", "are", "as", "at", "be", "been", "but", "by", "can",
    "could", "did", "do", "does", "for", "from", "had", "has", "have", "how", "i", "if",
    "in", "into", "is", "it", "its", "may", "me", "my", "no", "nor", "not", "of", "on",
    "or", "our", "shall", "should", "so", "some", "such", "than", "that", "the", "their",
    "them", "then", "there", "these", "they", "this", "those", "to", "under", "until",
    "up", "us", "was", "we", "were", "what", "when", "where", "which", "who", "whom",
    "why", "will", "with", "would", "you", "your",
})

# Words that appear in almost every policy section, so they do not help rank one
# section above another in this corpus.
_CORPUS_STOPWORDS = frozenset({
    "northwind", "robotics", "policy", "policies", "employee", "employees", "company",
})


def _sections_from_markish(text: str) -> list[tuple[str, str]]:
    """Split Markdown / plain-text policy content into (title, body) sections.

    Markdown headings start with ``#``. Plain-text policy files (``.txt``) use
    ALL-CAPS lines as section headings.
    """
    lines = text.splitlines()
    sections: list[tuple[str, str]] = []
    current_title = "Introduction"
    buffer: list[str] = []

    def is_caps_heading(line: str) -> bool:
        stripped = line.strip()
        if len(stripped) < 4 or len(stripped) > 80:
            return False
        letters = [c for c in stripped if c.isalpha()]
        return bool(letters) and all(c.isupper() for c in letters)

    for line in lines:
        stripped = line.strip()
        heading = None
        if stripped.startswith("#"):
            heading = stripped.lstrip("# ").strip()
        elif is_caps_heading(stripped):
            heading = stripped.title()

        if heading is not None:
            if buffer:
                sections.append((current_title, "\n".join(buffer).strip()))
            current_title = heading or "Introduction"
            buffer = []
        else:
            buffer.append(line)

    if buffer:
        sections.append((current_title, "\n".join(buffer).strip()))
    return sections


def _sections_from_html(text: str) -> list[tuple[str, str]]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(text, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()

    sections: list[tuple[str, str]] = []
    current_title = "Introduction"
    buffer: list[str] = []
    body = soup.body or soup
    for el in body.find_all(["h1", "h2", "h3", "p", "li"]):
        content = el.get_text(" ", strip=True)
        if not content:
            continue
        if el.name in ("h1", "h2", "h3"):
            if buffer:
                sections.append((current_title, "\n".join(buffer).strip()))
            current_title = content
            buffer = []
        else:
            buffer.append(f"- {content}" if el.name == "li" else content)
    if buffer:
        sections.append((current_title, "\n".join(buffer).strip()))
    return sections


def _sections_from_pdf(path: Path) -> list[tuple[str, str]]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    raw = "\n".join(page.extract_text() or "" for page in reader.pages)
    # The generated PDFs underline the document title with ``=`` and keep each
    # section heading on its own short line; normalise both to Markdown headings.
    normalised: list[str] = []
    prev = ""
    for line in raw.splitlines():
        if set(line.strip()) == {"="} and prev.strip():
            normalised[-1] = f"# {prev.strip()}"
        elif (
            line.strip()
            and not line.startswith(" ")
            and len(line.strip()) < 60
            and not line.strip().endswith((".", ",", ":", ";"))
        ):
            normalised.append(f"## {line.strip()}")
        else:
            normalised.append(line)
        prev = line
    return _sections_from_markish("\n".join(normalised))


def load_sections(path: Path) -> list[tuple[str, str]]:
    """Return (heading, body) sections for one corpus file, any supported format."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _sections_from_pdf(path)
    text = path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".html":
        return _sections_from_html(text)
    return _sections_from_markish(text)


def load_corpus_documents(corpus_dir: str | Path) -> list[Path]:
    corpus_path = Path(corpus_dir)
    docs: list[Path] = []
    for pattern in CORPUS_GLOBS:
        docs.extend(corpus_path.glob(pattern))
    return sorted(docs, key=lambda p: p.name)


def _query_terms(query: str) -> list[str]:
    """Content words from the query, lightly de-pluralised, deduplicated in order."""
    terms: list[str] = []
    for token in re.findall(r"[a-z0-9]+", query.lower()):
        if len(token) < 3 or token in _STOPWORDS or token in _CORPUS_STOPWORDS:
            continue
        # Fold a trailing plural "s" so "holidays" matches "holiday". Prefix
        # counting below also covers "accrue/accrual/accrued" from "accru".
        if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        if token not in terms:
            terms.append(token)
    return terms


def _count(term: str, text: str) -> int:
    """Word-prefix occurrences of ``term`` in ``text`` (already lower-cased)."""
    return len(re.findall(r"\b" + re.escape(term) + r"\w*", text))


def retrieve(query: str, corpus_dir: str | Path, k: int = 5) -> list[dict[str, str | float]]:
    """Return the most relevant policy passages for a query.

    A deliberately small, deterministic keyword retriever built to teach the pattern.
    It scans the multi-format corpus (Markdown, plain text, HTML, PDF), scores each
    section with prefix-matched term frequency weighted by inverse document frequency,
    normalised for section length, and boosted when a query term appears in the section
    heading or the document name. It returns the top matches with document id, section
    title, and a snippet.
    """
    docs = load_corpus_documents(corpus_dir)
    if not docs:
        raise FileNotFoundError(f"No corpus files found in {corpus_dir}")

    terms = _query_terms(query)
    if not terms and query.strip():
        terms = [query.strip().lower()]

    # Pass 1: collect every section with the fields scoring needs.
    records: list[dict] = []
    for doc in docs:
        stem_tokens = {
            t for t in doc.stem.split("-")
            if t.isalpha() and t not in _STOPWORDS and t not in _CORPUS_STOPWORDS
        }
        for title, body in load_sections(doc):
            if not body:
                continue
            records.append({
                "doc": doc,
                "title": title,
                "body": body,
                "body_lower": body.lower(),
                "title_lower": title.lower(),
                "stem_tokens": stem_tokens,
                "words": max(len(body.split()), 1),
            })

    if not records or not terms:
        return []

    # Inverse document frequency over sections, smoothed and always positive.
    n = len(records)
    idf: dict[str, float] = {}
    for term in terms:
        df = sum(1 for r in records if term in r["body_lower"])
        idf[term] = math.log((n + 1) / (1 + df)) + 1.0

    scored: list[tuple[float, str, str, dict]] = []
    for rec in records:
        tf_weight = sum(_count(term, rec["body_lower"]) * idf[term] for term in terms)
        if tf_weight <= 0:
            continue

        length_norm = 1.0 / (1.0 + math.log(1.0 + rec["words"] / 100.0))
        title_boost = sum(idf[term] for term in terms if _count(term, rec["title_lower"]))
        stem_boost = sum(idf[term] for term in terms if term in rec["stem_tokens"])
        score = tf_weight * length_norm + 2.5 * title_boost + 1.5 * stem_boost

        snippet = " ".join(rec["body"].strip().replace("\n", " ").split())
        if len(snippet) > 220:
            snippet = snippet[:217].rstrip() + "..."

        doc = rec["doc"]
        scored.append((score, doc.stem, rec["title"], {
            "doc_id": doc.stem,
            "title": doc.stem.replace("-", " ").title(),
            "section": rec["title"],
            "snippet": snippet,
            "source_format": doc.suffix.lstrip("."),
            "score": round(float(score), 4),
        }))

    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    return [match for _, _, _, match in scored[:k]]


def retrieve_passages(
    query: str,
    *,
    k: int | None = None,
    corpus_dir: str | Path | None = None,
) -> tuple[list[dict[str, str | float]], dict[str, str | None]]:
    """Retrieve policy passages, preferring the vector index, falling back to keyword.

    Returns ``(results, meta)`` where ``meta`` is ``{"method": "vector"|"keyword",
    "note": <why keyword, or None>}`` so callers can put the truth in the trace.
    """
    k = k or settings.retrieval_k
    corpus_dir = corpus_dir or DEFAULT_CORPUS_DIR

    from hr_agent import vector_store  # lazy: chunker -> retrieval import cycle

    note: str | None
    if not vector_store.index_exists():
        note = "no vector index (run scripts/build_index.py); used keyword search"
    elif not embedding_available():
        note = "GEMINI_API_KEY not set; used keyword search"
    else:
        try:
            query_vector = embed([query], task_type="retrieval_query")[0]
            return vector_store.search(query_vector, k), {"method": "vector", "note": None}
        except Exception as exc:  # noqa: BLE001 - degrade on any embedding/store failure
            logger.warning("vector retrieval failed; falling back to keyword: %s", exc)
            note = f"vector retrieval failed ({type(exc).__name__}); used keyword search"

    return retrieve(query, corpus_dir, k), {"method": "keyword", "note": note}
