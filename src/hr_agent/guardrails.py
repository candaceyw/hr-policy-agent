"""Retrieval-confidence guardrails: out-of-scope redirect and thin-evidence escalation.

The top retrieved passage's similarity score is a cheap, deterministic signal:
- below ``SCOPE_THRESHOLD``  -> the corpus almost certainly does not cover this;
  return a fixed redirect, no LLM call.
- in [SCOPE_THRESHOLD, ESCALATION_THRESHOLD) -> answer from context, but flag that
  the employee should confirm with HR.

The compose prompt is the second layer: it is told to refuse when the passages do
not actually answer the question. See :mod:`hr_agent.answering`.
"""

from __future__ import annotations

from collections.abc import Sequence

from hr_agent.config import settings

SCOPE_REFUSAL = (
    "I can only answer questions about Northwind Robotics HR policy -- time off, "
    "benefits, remote work, expenses, conduct, leave, pay, safety, and the like. "
    "That question looks outside that scope, so please redirect it to the right team "
    "(for example IT for account or device issues, or your manager for anything else)."
)


def top_score(results: Sequence[dict]) -> float:
    """Highest similarity among retrieved passages (0.0 when there are none)."""
    return max((float(r.get("score", 0.0)) for r in results), default=0.0)


def is_in_scope(results: Sequence[dict], *, threshold: float | None = None) -> bool:
    threshold = settings.scope_threshold if threshold is None else threshold
    return bool(results) and top_score(results) >= threshold


def needs_escalation(results: Sequence[dict], *, threshold: float | None = None) -> bool:
    """In scope, but the corpus coverage is thin enough to point the user to HR."""
    threshold = settings.escalation_threshold if threshold is None else threshold
    return is_in_scope(results) and top_score(results) < threshold
