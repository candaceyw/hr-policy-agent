from hr_agent.tools import plan_tool_workflow


def test_plan_tool_workflow_for_expense_check():
    workflow = plan_tool_workflow("Can I expense a company laptop and a home office chair?")
    assert workflow["needs_tool"] is True
    assert workflow["tool_name"] == "check_policy_compliance"
    assert workflow["reason"]


def test_plan_tool_workflow_for_basic_policy_question():
    workflow = plan_tool_workflow("How much PTO do employees accrue per month?")
    assert workflow["needs_tool"] is False
    assert workflow["tool_name"] == "none"
