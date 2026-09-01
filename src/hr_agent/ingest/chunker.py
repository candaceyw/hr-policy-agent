"""Deterministic, heading-aware chunking of the policy corpus.

Turns each corpus document into a list of :class:`PolicyChunk` records ready for
embedding. The strategy: walk the document's sections; within each section pack
whole sentences (and list/table rows) into windows of ``chunk_size`` tokens with
``chunk_overlap`` tokens of carry-over, never splitting a sentence; attach the
heading breadcrumb so a retrieved chunk can cite its own source section.

"Tokens" here are estimated as ``len(text) / 4`` -- a deterministic, offline
proxy that is accurate enough for *sizing*. Pass a different ``token_len`` to use
an exact tokenizer.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from hr_agent.retrieval import load_corpus_documents, load_sections

_APPROX_CHARS_PER_TOKEN = 4
_ATOMIC_PREFIXES = ("- ", "* ", "|", "#")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[\"'(\[]?[A-Z0-9])")


class PolicyChunk(BaseModel):
    chunk_id: str          # "<doc_id>#<chunk_index>"
    doc_id: str
    doc_title: str
    section_path: str      # "Benefits Guide > 401(k) Retirement Plan"
    chunk_index: int
    source_format: str     # md | txt | html | pdf
    text: str


def count_tokens_approx(text: str) -> int:
    """Deterministic offline token estimate (~4 characters per token)."""
    return max(1, -(-len(text) // _APPROX_CHARS_PER_TOKEN))


def split_units(text: str) -> list[str]:
    """Split a section body into atomic units: sentences, and list/table rows kept whole."""
    units: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(_ATOMIC_PREFIXES):
            units.append(line)
            continue
        units.extend(part.strip() for part in _SENTENCE_BOUNDARY.split(line) if part.strip())
    return units


def _pack_units(
    units: list[str], chunk_size: int, overlap: int, token_len: Callable[[str], int]
) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for unit in units:
        unit_tokens = token_len(unit)
        if current and current_tokens + unit_tokens > chunk_size:
            chunks.append(" ".join(current))
            tail: list[str] = []
            tail_tokens = 0
            for prev in reversed(current):
                prev_tokens = token_len(prev)
                if tail and tail_tokens + prev_tokens > overlap:
                    break
                tail.insert(0, prev)
                tail_tokens += prev_tokens
                if overlap <= 0:
                    break
            current = tail if overlap > 0 else []
            current_tokens = sum(token_len(u) for u in current)
        current.append(unit)
        current_tokens += unit_tokens

    if current:
        chunks.append(" ".join(current))
    return chunks


def chunk_corpus(
    corpus_dir: str | Path,
    *,
    chunk_size: int,
    chunk_overlap: int,
    token_len: Callable[[str], int] = count_tokens_approx,
) -> list[PolicyChunk]:
    """Chunk every document in ``corpus_dir`` deterministically."""
    chunks: list[PolicyChunk] = []
    for doc in load_corpus_documents(corpus_dir):
        doc_id = doc.stem
        doc_title = doc_id.replace("-", " ").title()
        source_format = doc.suffix.lstrip(".")
        chunk_index = 0
        for section_title, body in load_sections(doc):
            body = body.strip()
            if not body:
                continue
            section_path = f"{doc_title} > {section_title}"
            for text in _pack_units(split_units(body), chunk_size, chunk_overlap, token_len):
                chunks.append(
                    PolicyChunk(
                        chunk_id=f"{doc_id}#{chunk_index}",
                        doc_id=doc_id,
                        doc_title=doc_title,
                        section_path=section_path,
                        chunk_index=chunk_index,
                        source_format=source_format,
                        text=text,
                    )
                )
                chunk_index += 1
    return chunks


def chunks_content_hash(chunks: list[PolicyChunk]) -> str:
    """SHA-256 over chunk ids + text -- the value CI's ``--verify`` compares."""
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(f"{chunk.chunk_id}\x00{chunk.text}\x00".encode())
    return digest.hexdigest()
