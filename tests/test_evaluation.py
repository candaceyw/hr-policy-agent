"""Evaluation harness: gold-set validity, pure metrics, judge parsing, offline smoke."""

from __future__ import annotations

import json

import pytest

from evaluation import judges, metrics
from evaluation.run_eval import aggregate, render_results_md, run_item
from evaluation.schema import Category, load_items, load_smoke_items

CORPUS_STEMS = {
    "01-handbook-overview-and-code-of-conduct",
    "02-pto-and-vacation-policy",
    "03-holidays-and-company-closure",
    "04-remote-and-hybrid-work-policy",
    "05-out-of-state-and-international-remote-work",
    "06-data-security-and-acceptable-use",
    "07-expense-and-reimbursement-policy",
    "08-travel-policy",
    "09-benefits-guide",
    "10-leave-of-absence-policy",
    "11-onboarding-and-equipment-provisioning",
    "12-workplace-conduct-and-grievance-procedure",
    "13-compensation-and-payroll",
    "14-performance-and-development",
    "15-parental-and-family-leave",
    "16-workplace-health-and-safety",
    "17-information-classification-standard",
}


# --------------------------------------------------------------------- gold set


def test_gold_set_loads_and_covers_every_category():
    items = load_items()
    assert len(items) == 25
    seen = {it.category for it in items}
    assert seen == set(Category.__args__)  # all five categories present
    # >= 4 of each, so no category is a token entry.
    for cat in Category.__args__:
        assert sum(it.category == cat for it in items) >= 4


def test_gold_doc_ids_are_real_corpus_stems():
    for it in load_items():
        for doc_id in it.gold_doc_ids:
            assert doc_id in CORPUS_STEMS, f"{it.id}: unknown doc_id {doc_id!r}"


def test_gold_ids_unique_and_expectations_consistent():
    items = load_items()
    assert len({it.id for it in items}) == len(items)
    for it in items:
        if it.expected_behavior in ("clarify", "refuse"):
            assert not it.expected_tools and not it.gold_doc_ids
        if it.expected_behavior == "confirm":
            assert it.expected_tools  # a confirm item must name the gated tool


def test_smoke_subset_is_six_and_spans_behaviors():
    smoke = load_smoke_items()
    assert len(smoke) == 6
    assert {it.expected_behavior for it in smoke} >= {"answer", "clarify", "refuse", "confirm"}


def test_only_filter_selects_by_id_and_category():
    from evaluation.run_eval import _filter_items

    items = load_items()
    kept, unmatched = _filter_items(items, "md-01, out_of_scope , bogus-id")
    ids = {it.id for it in kept}
    assert "md-01" in ids
    assert all(it.category == "out_of_scope" or it.id == "md-01" for it in kept)
    assert {it.category for it in kept} == {"multi_doc", "out_of_scope"}
    assert unmatched == {"bogus-id"}

    citation_bearing, _ = _filter_items(items, "straightforward,multi_doc")
    assert len(citation_bearing) == 11
    assert all(it.gold_doc_ids for it in citation_bearing)


# --------------------------------------------------------------------- metrics


def test_prf_edge_cases():
    assert metrics.prf([], []) == {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    spurious = metrics.prf([], ["x"])
    assert spurious["precision"] == 0.0
    perfect = metrics.prf(["a", "b"], ["a", "b"])
    assert perfect == {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    half = metrics.prf(["a", "b"], ["a", "c"])
    assert half["precision"] == 0.5 and half["recall"] == 0.5


def test_jaccard():
    assert metrics.jaccard([], []) == 1.0
    assert metrics.jaccard(["a"], []) == 0.0
    assert metrics.jaccard(["a", "b"], ["a"]) == 0.5
    assert metrics.jaccard(["a"], ["a"]) == 1.0


def test_rouge_l_monotonic():
    gold = "Full-time employees accrue 10 hours of PTO per month."
    close = "Full-time staff accrue 10 hours of PTO each month."
    far = "The office is closed on federal holidays."
    assert metrics.rouge_l(gold, close) > metrics.rouge_l(gold, far)
    assert metrics.rouge_l(gold, "") == 0.0


def test_percentiles_interpolate():
    vals = [1.0, 2.0, 3.0, 4.0]
    p = metrics.percentiles(vals, (50, 95))
    assert p["p50"] == pytest.approx(2.5)
    assert p["p95"] == pytest.approx(3.85)
    assert metrics.percentiles([]) == {"p50": 0.0, "p95": 0.0}
    assert metrics.percentiles([7.0])["p95"] == 7.0


def test_observed_behavior_and_tools():
    clarify = {"intent": "clarify", "trace": [{"type": "clarify", "name": "request_clarification"}]}
    assert metrics.observed_behavior(clarify) == "clarify"
    refuse = {"intent": "out_of_scope"}
    assert metrics.observed_behavior(refuse) == "refuse"
    confirm = {"intent": "agentic_workflow", "pending_action": {"tool": "create_mock_hr_ticket"}}
    assert metrics.observed_behavior(confirm) == "confirm"
    answer = {
        "intent": "policy_qa",
        "answer": "10 hours",
        "trace": [
            {"type": "tool_call", "name": "search_policy_documents"},
            {"type": "compose", "name": "compose_answer"},
        ],
    }
    assert metrics.observed_behavior(answer) == "answer"
    assert metrics.observed_tools(answer) == ["search_policy_documents"]


def test_action_safe():
    gated = {"trace": [{"type": "tool_call", "name": "check_pto_balance"}], "pending_action": {}}
    assert metrics.action_safe(gated) is True
    bypassed = {"trace": [{"type": "tool_call", "name": "create_mock_hr_ticket"}]}
    assert metrics.action_safe(bypassed) is False
    assert metrics.action_safe(bypassed, confirmed=True) is True


def test_observed_doc_ids_dedupes_in_order():
    result = {
        "citations": [
            {"doc_id": "02-pto-and-vacation-policy"},
            {"doc_id": "02-pto-and-vacation-policy"},
            {"doc_id": "03-holidays-and-company-closure"},
        ]
    }
    assert metrics.observed_doc_ids(result) == [
        "02-pto-and-vacation-policy",
        "03-holidays-and-company-closure",
    ]


# --------------------------------------------------------------------- judge


def test_judge_parse_tolerates_prose_and_garbage():
    good = judges._parse('Here is my grade: {"score": 0.8, "rationale": "ok"}')
    assert good == {"score": 0.8, "rationale": "ok"}
    clamped = judges._parse('{"score": 5, "rationale": "x"}')
    assert clamped["score"] == 1.0
    junk = judges._parse("no json here")
    assert junk["score"] == 0.0


def test_judge_combined_one_call_two_scores():
    calls: list[str] = []

    def fake(prompt: str) -> str:
        calls.append(prompt)
        return (
            'sure: {"groundedness": {"score": 0.9, "rationale": "supported"}, '
            '"similarity": {"score": 0.4, "rationale": "missing a fact"}}'
        )

    v = judges.judge_combined("q", "ref", "an answer", "ctx", complete_fn=fake)
    assert len(calls) == 1  # halves judge requests vs two separate calls
    assert v["groundedness"]["score"] == 0.9
    assert v["similarity"]["score"] == 0.4
    # empty answer short-circuits without a model call
    v2 = judges.judge_combined("q", "ref", "  ", "ctx", complete_fn=fake)
    assert v2["groundedness"]["score"] == 0.0 and len(calls) == 1
    # unparseable reply -> zeros, not a crash
    v3 = judges.judge_combined("q", "ref", "a", "ctx", complete_fn=lambda _p: "nope")
    assert v3["groundedness"]["score"] == 0.0 and v3["similarity"]["score"] == 0.0


def test_judge_functions_use_injected_complete_fn():
    calls: list[str] = []

    def fake(prompt: str) -> str:
        calls.append(prompt)
        return '{"score": 0.75, "rationale": "supported"}'

    g = judges.judge_groundedness("q", "a", "ctx", complete_fn=fake)
    s = judges.judge_similarity("q", "ref", "a", complete_fn=fake)
    assert g["score"] == 0.75 and s["score"] == 0.75
    assert len(calls) == 2
    # empty answer / context short-circuit without calling the model
    assert judges.judge_groundedness("q", "", "ctx", complete_fn=fake)["score"] == 0.0
    assert judges.judge_similarity("q", "ref", "", complete_fn=fake)["score"] == 0.0
    assert len(calls) == 2


# --------------------------------------------------------------------- aggregate


def _record(**over):
    base = {
        "id": "x",
        "category": "straightforward",
        "is_workflow": False,
        "latency_s": 1.0,
        "error": None,
        "expected_behavior": "answer",
        "observed_behavior": "answer",
        "behavior_match": True,
        "tool_jaccard": 1.0,
        "action_safe": True,
        "completed": True,
    }
    base.update(over)
    return base


def test_aggregate_shapes_rubric_metrics():
    records = [
        _record(id="a", citation={"precision": 1.0, "recall": 1.0, "f1": 1.0},
                rouge_l=0.6, groundedness=0.9, similarity=0.8),
        _record(id="b", category="tool", is_workflow=True, expected_tools=["check_pto_balance"],
                rouge_l=0.4, groundedness=0.7, similarity=0.6),
        _record(id="c", category="ambiguous", expected_behavior="clarify",
                observed_behavior="clarify", tool_jaccard=1.0),
        _record(id="d", category="out_of_scope", expected_behavior="refuse",
                observed_behavior="answer", behavior_match=False, completed=False),
    ]
    s = aggregate(records)
    assert s["n"] == 4
    assert s["answer_quality"]["groundedness"] == pytest.approx(0.8)
    assert s["answer_quality"]["citation"]["f1"] == pytest.approx(1.0)
    assert s["agent_behavior"]["action_safety_pass_rate"] == 1.0
    assert s["agent_behavior"]["gate_accuracy"] == pytest.approx(0.5)  # c right, d wrong
    assert s["agent_behavior"]["workflow_completion_rate"] == 1.0  # only b
    assert s["system"]["latency_p50_s"] == 1.0
    md = render_results_md(s, {
        "timestamp": "t", "mode": "full (25 items)", "llm_provider": "groq",
        "llm_model": "m", "judge_model": "g", "judge": True, "offline": False,
        "results_file": "eval-t.json",
    })
    assert "# Evaluation results" in md and "Action-safety pass rate" in md


# --------------------------------------------------------------------- offline smoke


@pytest.mark.slow
def test_offline_smoke_run_produces_well_formed_records():
    """Drive the 6-item subset with a stub model -- no provider, no judge."""
    from evaluation.run_eval import _build_offline_model

    model = _build_offline_model()
    records = [run_item(it, model=model, judge=False) for it in load_smoke_items()]
    assert len(records) == 6
    for rec in records:
        assert rec["observed_behavior"] in ("answer", "clarify", "refuse", "confirm")
        assert 0.0 <= rec["tool_jaccard"] <= 1.0
        assert isinstance(rec["action_safe"], bool)
        assert rec["latency_s"] >= 0.0
    summary = aggregate(records)
    # round-trips as JSON (what run_eval writes to results/)
    json.dumps({"summary": summary, "records": records})
    assert summary["agent_behavior"]["action_safety_pass_rate"] == 1.0
