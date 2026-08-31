"""Unit tests for the deterministic pre-agent gate (hr_agent.agent.gate)."""

from __future__ import annotations

from hr_agent.agent.gate import decide, looks_ambiguous, wants_employee_workflow


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
    d = decide(
        "What is the weather tomorrow?",
        retrieval_results=[{"score": 0.31}],
        retrieval_method="vector",
    )
    assert d.route == "scope"
    assert d.intent == "out_of_scope"


def test_keyword_retrieval_never_triggers_scope_refusal():
    # TF-IDF scores are not calibrated 0-1, so the gate fails open on them.
    d = decide(
        "What is the weather tomorrow?",
        retrieval_results=[{"score": 0.31}],
        retrieval_method="keyword",
    )
    assert d.route == "agent"


def test_wants_employee_workflow_detects_mock_actions_and_personal_topics():
    assert wants_employee_workflow("Please open an HR ticket about my broken laptop")
    assert wants_employee_workflow("draft an email to my manager about time off")
    assert wants_employee_workflow("what is my PTO balance")
    assert not wants_employee_workflow("what is the PTO accrual rate")
