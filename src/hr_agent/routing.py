from __future__ import annotations


def classify_intent(query: str) -> str:
    """Very small intent classifier for learning purposes.

    This is intentionally simple and explicit, so the concept is easy to explain:
    a router decides the type of request before any retrieval or tool use.
    """
    lowered = query.lower()

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

    if intent == "employee_data_request":
        return {
            "intent": intent,
            "needs_tools": True,
            "reason": "This request needs employee data and likely a PTO or benefits lookup before giving a final answer.",
        }

    if intent == "expense_check":
        return {
            "intent": intent,
            "needs_tools": True,
            "reason": "Expense eligibility usually depends on policy and may require a compliance check.",
        }

    if intent == "policy_question":
        return {
            "intent": intent,
            "needs_tools": False,
            "reason": "This can likely be answered from the policy corpus with retrieval.",
        }

    return {
        "intent": intent,
        "needs_tools": False,
        "reason": "No special policy routing decision is needed for this request.",
    }
