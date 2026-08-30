from hr_agent.routing import classify_intent, route_query


def test_classify_intent_for_policy_question():
    assert classify_intent("How much PTO do employees accrue per month?") == "policy_question"


def test_route_query_marks_tool_needed_for_expense_request():
    result = route_query("Can I expense a company laptop and a home office chair?")
    assert result["intent"] == "expense_check"
    assert result["needs_tools"] is True
    assert result["reason"]


def test_classify_intent_for_ticket_request_beats_expense_keywords():
    query = "Create a mock HR ticket for employee E-1001 about laptop reimbursement."
    assert classify_intent(query) == "ticket_request"


def test_classify_intent_for_email_request():
    assert classify_intent("Draft an email to my manager about my PTO request.") == "email_request"


def test_route_query_marks_ticket_request_destructive():
    result = route_query("Please open an HR ticket about my broken laptop.")
    assert result["intent"] == "ticket_request"
    assert result["needs_tools"] is True
    assert result["destructive"] is True


def test_named_employee_routes_to_employee_data_request():
    assert classify_intent("How much PTO does E-1002 have?") == "employee_data_request"
    assert classify_intent("How much PTO does Marcus Silva have?") == "employee_data_request"


def test_common_word_surname_does_not_trigger_employee_routing():
    # "foster" is a surname in the mock data but also an ordinary word.
    assert classify_intent("How much parental leave do I get for a foster placement?") == "policy_question"
