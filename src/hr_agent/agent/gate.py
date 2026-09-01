"""Deterministic pre-agent gate: ``classify_intent -> clarify | scope | agent``.

No LLM call. Three cheap signals decide the route before the agent loop runs:

* **employee resolution** (:mod:`hr_agent.directory`) -- a workflow that needs a
  specific person but names none, or names one we have no record of, is sent to
  ``clarify`` instead of letting the model invent a profile.
* **ambiguity** -- a bare first-person yes/no question with almost no content
  ("Am I eligible?") is sent to ``clarify`` for exactly one follow-up question.
* **retrieval scope score** (:mod:`hr_agent.guardrails`) -- only meaningful when
  vector retrieval ran; a policy question the corpus does not cover is sent to
  ``scope`` for a fixed redirect.

Everything else goes to ``agent``, which already does policy-vs-workflow and
tool selection itself. This module is pure and import-cheap so the graph stays
testable without a model or a network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from hr_agent.directory import get_employee_name, resolve_employee
from hr_agent.guardrails import is_in_scope
from hr_agent.routing import EMAIL_PHRASES, TICKET_PHRASES

Route = Literal["agent", "clarify", "scope"]

# First-person possessive about a person-specific HR topic, or a bare balance
# query. "how much PTO do I have" is personal; "how much PTO do employees
# accrue" is a policy question, so the how-much clause requires a nearby "I"/"my".
_PERSONAL_TOPIC_RE = re.compile(
    r"\b(my|mine)\b[^.?!]*\b(pto|vacation|leave|balance|benefits?|profile|"
    r"coverage|enroll?ment|401\(?k\)?|paycheck|salary|pay stub)\b"
    r"|\b(pto|vacation|leave)\s+balance\b"
    r"|\bhow\s+much\s+(pto|vacation|leave|time\s*off)\b(?=[^.?!]*\b(i|my)\b)",
    re.IGNORECASE,
)

# "take three days off next week", "book PTO for Monday", "time off next week".
_TIME_OFF_REQUEST_RE = re.compile(
    r"\b(take|book|request|use|schedule|put in for)\b[^.?!]*\b"
    r"(day|days|hour|hours|week|weeks|pto|vacation|leave|time\s*off)\b"
    r"|\b(time\s*off|pto|vacation|leave)\b[^.?!]*\b(next|this)\s+(week|month|monday|"
    r"tuesday|wednesday|thursday|friday)\b",
    re.IGNORECASE,
)

# Remote-work / relocation eligibility asked about a person.
_ELIGIBILITY_RE = re.compile(
    r"\b(work(ing)?|working)\b[^.?!]*\b(remotely|from\s+home|abroad|overseas|"
    r"from\s+(another|a\s+different)\s+state|out\s+of\s+state|from\s+[A-Z][a-z]+)\b"
    r"|\b(am\s+i|is\s+\w+|are\s+they)\b[^.?!]*\b(eligible|allowed|approved|able)\b",
    re.IGNORECASE,
)

_MOCK_ACTION_PHRASES = tuple(TICKET_PHRASES) + tuple(EMAIL_PHRASES)

# Bleached verbs that add no content when counting how specific a question is.
_BLEACHED = frozenset({"get", "take", "use", "go", "do", "have", "make", "put"})
_STOP = frozenset({
    "a", "an", "the", "i", "we", "my", "me", "is", "it", "to", "of", "for", "and",
    "or", "can", "could", "may", "am", "are", "do", "does", "if", "in", "on", "at",
    "be", "this", "that", "next", "with", "from", "any", "some",
})
_FIRST_PERSON_Q_RE = re.compile(r"^\s*(can|could|may|do|am)\s+i\b[^?]*\?*\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class GateDecision:
    route: Route
    intent: str
    employee_id: str | None = None
    message: str | None = None  # clarify question or scope-refusal text


def wants_employee_workflow(query: str) -> bool:
    """True when the request is about one specific person's data or a mock action."""
    lowered = query.lower()
    if any(phrase in lowered for phrase in _MOCK_ACTION_PHRASES):
        return True
    return bool(
        _PERSONAL_TOPIC_RE.search(query)
        or _TIME_OFF_REQUEST_RE.search(query)
        or _ELIGIBILITY_RE.search(query)
    )


def _content_tokens(query: str) -> list[str]:
    return [
        t
        for t in re.findall(r"[a-z0-9]+", query.lower())
        if t not in _STOP and t not in _BLEACHED and len(t) > 1
    ]


def looks_ambiguous(query: str) -> bool:
    """A bare first-person yes/no question with <= 2 content words ("Am I eligible?")."""
    return bool(_FIRST_PERSON_Q_RE.match(query.strip())) and len(_content_tokens(query)) <= 2


def _clarify_message(*, unknown_id: str | None, ambiguous: bool) -> str:
    if unknown_id:
        return (
            f"I don't have a record for employee {unknown_id}. "
            "Double-check the id (it looks like E-1002) and I can pull the details."
        )
    if ambiguous:
        return (
            "I want to answer the right thing -- could you say a bit more about what "
            "you need (the specific policy, benefit, or expense, and any dates)?"
        )
    return (
        "Which employee is this for? Share the employee id (for example E-1002) and "
        "I'll look up the details."
    )


def decide(
    query: str,
    *,
    employee_id_hint: str | None = None,
    retrieval_results: list[dict] | None = None,
    retrieval_method: str | None = None,
    has_history: bool = False,
) -> GateDecision:
    """Route the request. Pure: callers pass any retrieval output in.

    ``retrieval_results`` / ``retrieval_method`` come from
    :func:`hr_agent.retrieval.retrieve_passages`; scope is only enforced when
    ``retrieval_method == "vector"`` (keyword scores are not calibrated 0-1).
    ``has_history`` True means this is a follow-up in an open conversation, so
    the out-of-scope guardrail is skipped -- a short follow-up ("what about
    abroad?") scores low on its own but is almost certainly still on topic.

    ``employee_id_hint`` (the session's selected employee) only *fills in* a
    person when the query itself needs one -- it never makes a generic policy
    question ("how much PTO do employees accrue?") into a personal workflow.
    """
    query_employee = resolve_employee(query)
    personal = wants_employee_workflow(query) or bool(query_employee)
    resolved = query_employee or (employee_id_hint if personal else None)
    known = bool(resolved and get_employee_name(resolved))
    ambiguous = looks_ambiguous(query)
    intent = "agentic_workflow" if personal else ("ambiguous" if ambiguous else "policy_qa")

    # 1. Named an employee we don't have -> redirect, never fabricate.
    if resolved and not known:
        return GateDecision(
            "clarify", intent, None, _clarify_message(unknown_id=resolved, ambiguous=False)
        )

    # 2. Too vague to act on without guessing -> ask what they need. Checked
    #    before the "which employee?" branch so a bare "Am I eligible?" gets the
    #    useful question, not a request for an id we can't yet use.
    if ambiguous:
        return GateDecision(
            "clarify", "ambiguous", None, _clarify_message(unknown_id=None, ambiguous=True)
        )

    # 3. Needs a specific person, none given -> ask which.
    if personal and not resolved:
        return GateDecision(
            "clarify", intent, None, _clarify_message(unknown_id=None, ambiguous=False)
        )

    # 4. Plain policy question the corpus does not cover (vector signal only,
    #    and never on a follow-up -- see has_history).
    if (
        not personal
        and not has_history
        and retrieval_method == "vector"
        and not is_in_scope(retrieval_results or [])
    ):
        return GateDecision("scope", "out_of_scope", None, None)

    return GateDecision("agent", intent, resolved if known else None, None)
