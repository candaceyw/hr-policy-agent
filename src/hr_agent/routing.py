from __future__ import annotations

from hr_agent.directory import resolve_employee

TICKET_PHRASES = (
    "create a ticket",
    "create an hr ticket",
    "create a mock hr ticket",
    "create a mock ticket",
    "open a ticket",
    "open an hr ticket",
    "open a case",
    "open an hr case",
    "file a ticket",
    "raise a ticket",
    "raise a case",
    "log a ticket",
    "submit a ticket",
    "hr ticket",
    "hr case",
)

EMAIL_PHRASES = (
    "draft an email",
    "draft a note",
    "draft an hr email",
    "draft a message",
    "write an email",
    "write a note",
    "send an email",
    "email my manager",
    "email to my manager",
    "email hr",
)


def classify_intent(query: str) -> str:
    """Very small intent classifier for learning purposes.

    This is intentionally simple and explicit, so the concept is easy to explain:
    a router decides the type of request before any retrieval or tool use. The
    mock-action intents (ticket / email) are checked first so an explicit request
    like "create a ticket about my laptop" is not swallowed by the expense keywords.
    """
    lowered = query.lower()

    if any(phrase in lowered for phrase in TICKET_PHRASES):
        return "ticket_request"
    if any(phrase in lowered for phrase in EMAIL_PHRASES):
        return "email_request"

    # A specific employee named in the query (by id or full name) means the
    # request needs that employee's structured data, not a generic policy answer.
    if resolve_employee(query, allow_partial=False) is not None:
        return "employee_data_request"

    if "employee profile" in lowered or "profile for" in lowered or "show me the employee" in lowered:
        return "employee_data_request"
    if "pto balance" in lowered or "pto" in lowered and "balance" in lowered:
        return "employee_data_request"
    if any(word in lowered for word in ["expense", "reimburse", "claim", "receipt", "laptop", "chair", "trip"]):
        return "expense_check"
    if any(word in lowered for word in ["pto", "vacation", "holiday", "benefit", "policy", "leave", "remote", "travel", "conduct"]):
        return "policy_question"
    if any(word in lowered for word in ["benefits", "enroll", "coverage", "deductible", "plan"]):
        return "benefits_question"
    return "general_question"


def route_query(query: str) -> dict:
    intent = classify_intent(query)

    if intent == "ticket_request":
        return {
            "intent": intent,
            "needs_tools": True,
            "destructive": True,
            "reason": "Creating an HR ticket is a mock action and must be confirmed before it runs.",
        }

    if intent == "email_request":
        return {
            "intent": intent,
            "needs_tools": True,
            "destructive": True,
            "reason": "Drafting an HR email is a mock action and must be confirmed before it runs.",
        }

    if intent == "employee_data_request":
        return {
            "intent": intent,
            "needs_tools": True,
            "destructive": False,
            "reason": "This request needs employee data and likely a PTO or benefits lookup before giving a final answer.",
        }

    if intent == "expense_check":
        return {
            "intent": intent,
            "needs_tools": True,
            "destructive": False,
            "reason": "Expense eligibility usually depends on policy and may require a compliance check.",
        }

    if intent == "policy_question":
        return {
            "intent": intent,
            "needs_tools": False,
            "destructive": False,
            "reason": "This can likely be answered from the policy corpus with retrieval.",
        }

    return {
        "intent": intent,
        "needs_tools": False,
        "destructive": False,
        "reason": "No special policy routing decision is needed for this request.",
    }
