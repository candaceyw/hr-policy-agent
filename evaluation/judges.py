"""LLM-judge metrics: groundedness and answer similarity.

The judge is a separate model from the system under test (see ``config.py``:
``EVAL_JUDGE_PROVIDER`` / ``EVAL_JUDGE_MODEL``) so it does not grade its own
output. All model access goes through ``hr_agent.llm.judge_complete`` -- this
module never imports a model SDK.

Every function accepts ``complete_fn`` so tests can inject a fake and run offline.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable

from hr_agent.config import settings
from hr_agent.llm import judge_complete

CompleteFn = Callable[[str], str]

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

_GROUNDEDNESS_PROMPT = """\
You are grading whether an HR assistant's ANSWER is supported by the CONTEXT it \
was given. Only the CONTEXT counts as evidence; outside knowledge does not.

Score from 0.0 to 1.0:
- 1.0  every factual claim in the answer is directly supported by the context
- 0.5  the answer is mostly supported but has one unsupported or overreaching claim
- 0.0  key claims are unsupported, contradicted, or fabricated

QUESTION:
{query}

CONTEXT:
{context}

ANSWER:
{answer}

Reply with JSON only: {{"score": <float>, "rationale": "<one sentence>"}}
"""

_SIMILARITY_PROMPT = """\
You are grading whether an HR assistant's ANSWER matches the REFERENCE answer on \
substance (the facts and figures), ignoring wording, length, and citation style.

Score from 0.0 to 1.0:
- 1.0  same key facts and numbers as the reference
- 0.5  partially correct, or missing a key fact, or one wrong detail
- 0.0  wrong, contradictory, or non-responsive

QUESTION:
{query}

REFERENCE:
{reference}

ANSWER:
{answer}

Reply with JSON only: {{"score": <float>, "rationale": "<one sentence>"}}
"""


def _parse(text: str) -> dict:
    match = _JSON_RE.search(text or "")
    if not match:
        return {"score": 0.0, "rationale": f"unparseable judge reply: {text[:120]!r}"}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"score": 0.0, "rationale": f"invalid judge JSON: {text[:120]!r}"}
    try:
        score = float(data.get("score"))
    except (TypeError, ValueError):
        score = 0.0
    return {"score": max(0.0, min(1.0, score)), "rationale": str(data.get("rationale", ""))}


class JudgeUnavailable(RuntimeError):
    """The judge model could not be reached after retries (429/503/network)."""


def _default_complete(prompt: str, *, retries: int = 4) -> str:
    """Call the configured judge with backoff on transient errors, then pace.

    Free-tier judges throw 429 (rate) and 503 (high demand) under load; a single
    blip must not abort a 25-item run, so retry a few times and then raise a
    typed error the runner records as a missing score.
    """
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            out = judge_complete(prompt)
            if settings.eval_judge_pace_seconds > 0:
                time.sleep(settings.eval_judge_pace_seconds)
            return out
        except Exception as exc:  # noqa: BLE001 - provider SDKs raise varied types
            last = exc
            transient = any(code in str(exc) for code in ("429", "503", "500", "UNAVAILABLE"))
            if not transient or attempt == retries:
                break
            time.sleep(min(2.0**attempt, 30.0) + settings.eval_judge_pace_seconds)
    raise JudgeUnavailable(f"judge call failed: {last}") from last


def judge_groundedness(
    query: str,
    answer: str,
    context: str,
    *,
    complete_fn: CompleteFn | None = None,
) -> dict:
    """Is every claim in ``answer`` supported by ``context``? Score 0-1."""
    if not answer.strip() or not context.strip():
        return {"score": 0.0, "rationale": "no answer or no context to ground against"}
    fn = complete_fn or _default_complete
    prompt = _GROUNDEDNESS_PROMPT.format(query=query, context=context, answer=answer)
    return _parse(fn(prompt))


def judge_similarity(
    query: str,
    reference: str,
    answer: str,
    *,
    complete_fn: CompleteFn | None = None,
) -> dict:
    """Does ``answer`` carry the same substance as the short gold ``reference``? 0-1."""
    if not answer.strip():
        return {"score": 0.0, "rationale": "empty answer"}
    fn = complete_fn or _default_complete
    prompt = _SIMILARITY_PROMPT.format(query=query, reference=reference, answer=answer)
    return _parse(fn(prompt))
