from hr_agent.config import settings
from hr_agent.guardrails import (
    SCOPE_REFUSAL,
    is_in_scope,
    needs_escalation,
    top_score,
)


def _hits(*scores):
    return [{"doc_id": "d", "title": "T", "section": "S", "snippet": "x", "score": s} for s in scores]


def test_top_score_picks_the_max_and_handles_empty():
    assert top_score(_hits(0.3, 0.71, 0.5)) == 0.71
    assert top_score([]) == 0.0


def test_in_scope_uses_the_threshold():
    assert is_in_scope(_hits(0.80, 0.4)) is True
    assert is_in_scope(_hits(0.50, 0.49)) is False
    assert is_in_scope([]) is False


def test_needs_escalation_is_the_thin_middle_band():
    below = settings.scope_threshold - 0.01
    thin = (settings.scope_threshold + settings.escalation_threshold) / 2
    strong = settings.escalation_threshold + 0.1
    assert needs_escalation(_hits(below)) is False   # out of scope, not escalation
    assert needs_escalation(_hits(thin)) is True     # in scope but thin
    assert needs_escalation(_hits(strong)) is False  # solid evidence


def test_scope_refusal_text_points_elsewhere():
    assert "HR policy" in SCOPE_REFUSAL
    assert "IT" in SCOPE_REFUSAL
