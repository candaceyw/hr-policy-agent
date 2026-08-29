from hr_agent.orchestration import run_workflow


def test_run_workflow_handles_policy_question():
    result = run_workflow("How much PTO do employees accrue per month?")
    assert result["intent"] == "policy_question"
    assert result["answer"]
    assert result["citations"]


def test_run_workflow_handles_expense_check():
    result = run_workflow("Can I expense a company laptop and a home office chair?")
    assert result["intent"] == "expense_check"
    assert result["needs_tool"] is True
    assert result["tool_name"] == "check_policy_compliance"
