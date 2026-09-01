"""Unit tests for the deterministic pre-agent gate (hr_agent.agent.gate)."""

from __future__ import annotations

import pytest

from hr_agent.agent.gate import (
    decide,
    looks_ambiguous,
    looks_off_topic,
    wants_employee_workflow,
)


def test_named_known_employee_routes_to_agent():
    d = decide("How much PTO does Marcus Silva have left?")
    assert d.route == "agent"
    assert d.employee_id == "E-1002"
    assert d.intent == "agentic_workflow"


def test_unknown_employee_id_routes_to_clarify_without_fabricating():
    d = decide("Show me the profile for E-9999")
    assert d.route == "clarify"
    assert d.employee_id is None
    assert "E-9999" in d.message


def test_personal_workflow_without_any_employee_asks_which_one():
    d = decide("Can I take three days of PTO next week?")
    assert d.route == "clarify"
    assert "employee id" in d.message.lower()


def test_session_employee_id_hint_satisfies_a_personal_workflow():
    d = decide("Can I take three days of PTO next week?", employee_id_hint="E-1002")
    assert d.route == "agent"
    assert d.employee_id == "E-1002"


def test_selected_employee_does_not_make_a_generic_policy_question_personal():
    # A session employee is selected, but the question is about everyone.
    d = decide("How much PTO do employees accrue per month?", employee_id_hint="E-1002")
    assert d.route == "agent"
    assert d.intent == "policy_qa"
    assert d.employee_id is None


def test_how_much_pto_is_personal_only_in_first_person():
    assert wants_employee_workflow("how much PTO do I have")
    assert not wants_employee_workflow("how much PTO do employees accrue per month")


def test_bare_first_person_question_is_ambiguous():
    assert looks_ambiguous("Am I eligible?")
    assert looks_ambiguous("Can I get reimbursed?")
    d = decide("Am I eligible?")
    assert d.route == "clarify"
    assert d.intent == "ambiguous"


def test_specific_policy_question_is_not_ambiguous():
    assert not looks_ambiguous("How much PTO do I accrue per month?")
    assert not looks_ambiguous("Can I work from Ireland for six weeks with my laptop?")


def test_plain_policy_question_routes_to_agent_when_in_scope():
    d = decide(
        "What is the holiday schedule?",
        retrieval_results=[{"score": 0.72}],
        retrieval_method="vector",
    )
    assert d.route == "agent"
    assert d.intent == "policy_qa"


def test_out_of_scope_policy_question_routes_to_scope_on_vector_signal():
    # A low vector score with no off-topic keyword -> the score path alone.
    d = decide(
        "Tell me about quantum entanglement.",
        retrieval_results=[{"score": 0.31}],
        retrieval_method="vector",
    )
    assert d.route == "scope"
    assert d.intent == "out_of_scope"


def test_keyword_retrieval_never_triggers_scope_refusal_on_score_alone():
    # TF-IDF scores are not calibrated 0-1, so the gate fails open on a low
    # score when nothing else marks the query as off-topic.
    d = decide(
        "Tell me about quantum entanglement.",
        retrieval_results=[{"score": 0.31}],
        retrieval_method="keyword",
    )
    assert d.route == "agent"


@pytest.mark.parametrize(
    "query",
    [
        "What's the weather in Austin tomorrow?",
        "Write me a Python function that reverses a linked list.",
        "What's a good recipe for dinner tonight?",
        "Who is the current CEO of Google?",
    ],
)
def test_off_topic_keyword_routes_to_scope_regardless_of_retrieval_score(query):
    # Even with a high-scoring stray policy chunk, an explicit off-topic query
    # is redirected. These four are the eval gold out-of-scope set.
    assert looks_off_topic(query)
    d = decide(query, retrieval_results=[{"score": 0.91}], retrieval_method="vector")
    assert d.route == "scope"
    assert d.intent == "out_of_scope"


def test_off_topic_filter_is_method_independent():
    # Unlike the score guardrail, the keyword filter also fires on keyword
    # retrieval -- it is a match, not a calibrated score.
    d = decide(
        "What's the weather in Austin tomorrow?",
        retrieval_results=[{"score": 0.42}],
        retrieval_method="keyword",
    )
    assert d.route == "scope"


def test_off_topic_filter_exempts_personal_workflows():
    # "good recipe" matches the off-topic filter, but this is a mock-email
    # workflow for a known employee -> the filter is skipped, the workflow runs.
    query = "Draft an email to my manager about a good recipe for the team potluck."
    assert looks_off_topic(query)
    d = decide(query, employee_id_hint="E-1002")
    assert d.route == "agent"
    assert d.employee_id == "E-1002"
    assert d.intent == "agentic_workflow"


def test_looks_off_topic_leaves_real_policy_questions_alone():
    assert not looks_off_topic("Does Northwind close the office for snow days?")
    assert not looks_off_topic("What is the holiday schedule?")
    assert not looks_off_topic("How do I submit an expense report?")
    assert not looks_off_topic("Who is my manager?")


def test_wants_employee_workflow_detects_mock_actions_and_personal_topics():
    assert wants_employee_workflow("Please open an HR ticket about my broken laptop")
    assert wants_employee_workflow("draft an email to my manager about time off")
    assert wants_employee_workflow("what is my PTO balance")
    assert not wants_employee_workflow("what is the PTO accrual rate")
