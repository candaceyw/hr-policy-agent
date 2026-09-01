import math

import pytest

from hr_agent.config import settings
from hr_agent.llm import embed, embedding_available

pytestmark = pytest.mark.skipif(
    not embedding_available(), reason="GEMINI_API_KEY not set; live embedding test skipped"
)


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def test_embed_returns_normalised_vectors_of_configured_dim():
    vecs = embed(["hello world", "goodbye world"], task_type="retrieval_document")
    assert len(vecs) == 2
    for v in vecs:
        assert len(v) == settings.embedding_dim
        assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, abs_tol=1e-3)


def test_embed_captures_meaning_not_shared_words():
    docs = embed(
        [
            "Full-time employees accrue ten hours of PTO each month.",
            "The office is closed on federal holidays.",
        ],
        task_type="retrieval_document",
    )
    query = embed(["how much paid time off do I get monthly"], task_type="retrieval_query")[0]
    # The query shares no words with doc 0 ("PTO" vs "paid time off") yet must rank it first.
    assert _cos(query, docs[0]) > _cos(query, docs[1])


def test_embed_empty_list_is_a_noop():
    assert embed([]) == []
