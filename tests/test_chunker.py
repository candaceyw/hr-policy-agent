from pathlib import Path

from hr_agent.ingest.chunker import (
    chunk_corpus,
    chunks_content_hash,
    count_tokens_approx,
    split_units,
)

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "corpus"

CHUNK_SIZE = 200
OVERLAP = 40


def _chunks():
    return chunk_corpus(CORPUS, chunk_size=CHUNK_SIZE, chunk_overlap=OVERLAP)


def test_count_tokens_approx_is_four_chars_per_token():
    assert count_tokens_approx("") == 1
    assert count_tokens_approx("abcd") == 1
    assert count_tokens_approx("a" * 800) == 200


def test_chunking_is_deterministic():
    a = _chunks()
    b = _chunks()
    assert [c.chunk_id for c in a] == [c.chunk_id for c in b]
    assert chunks_content_hash(a) == chunks_content_hash(b)


def test_every_chunk_carries_a_heading_breadcrumb():
    for chunk in _chunks():
        assert " > " in chunk.section_path
        assert chunk.section_path.startswith(chunk.doc_title)
        assert chunk.text.strip()


def test_chunk_index_is_contiguous_per_document():
    by_doc: dict[str, list[int]] = {}
    for chunk in _chunks():
        by_doc.setdefault(chunk.doc_id, []).append(chunk.chunk_index)
    for indices in by_doc.values():
        assert indices == list(range(len(indices)))


def test_chunks_respect_the_size_cap_with_slack_for_one_long_sentence():
    for chunk in _chunks():
        # A chunk may overshoot by at most the largest single unit it contains.
        longest_unit = max((count_tokens_approx(u) for u in split_units(chunk.text)), default=0)
        assert count_tokens_approx(chunk.text) <= CHUNK_SIZE + longest_unit


def test_all_four_source_formats_are_chunked():
    formats = {c.source_format for c in _chunks()}
    assert {"md", "pdf", "html", "txt"} <= formats


def test_sentences_are_never_split_and_adjacent_chunks_overlap():
    section = " ".join(f"Sentence number {i} states a distinct rule." for i in range(40))
    text = f"# Doc\n\n## Section\n{section}\n"
    tmp = Path(__file__).resolve().parents[1] / "corpus" / "_tmp_chunk_fixture.md"
    tmp.write_text(text, encoding="utf-8")
    try:
        chunks = [c for c in _chunks() if c.doc_id == "_tmp_chunk_fixture"]
        assert len(chunks) >= 2
        units = split_units(section)
        # no sentence is cut: every unit appears verbatim in some chunk
        for unit in units:
            assert any(unit in c.text for c in chunks)
        # overlap: the first chunk's final sentence reappears in the second chunk
        first_last_sentence = split_units(chunks[0].text)[-1]
        assert first_last_sentence in chunks[1].text
    finally:
        tmp.unlink()
