from hr_agent.routing import classify_intent, route_query


def test_classify_intent_for_policy_question():
    assert classify_intent("How much PTO do employees accrue per month?") == "policy_question"


def test_route_query_marks_tool_needed_for_expense_request():
    result = route_query("Can I expense a company laptop and a home office chair?")
    assert result["intent"] == "expense_check"
    assert result["needs_tools"] is True
    assert result["reason"]
