from __future__ import annotations

from hr_agent.routing import route_query


def plan_tool_workflow(query: str) -> dict:
    """Map a request to a simple tool workflow.

    This is the teaching bridge between routing and an actual agent system:
    route -> decide whether a tool is needed -> choose a tool name -> explain why.
    """
    decision = route_query(query)

    if decision["intent"] == "employee_data_request":
        lowered = query.lower()
        if "pto" in lowered and "balance" in lowered:
            return {
                "needs_tool": True,
                "tool_name": "check_pto_balance",
                "reason": "This request requires the employee's PTO record before answering accurately.",
            }
        return {
            "needs_tool": True,
            "tool_name": "lookup_employee_profile",
            "reason": "This request needs structured employee data to answer accurately.",
        }

    if decision["intent"] == "expense_check":
        return {
            "needs_tool": True,
            "tool_name": "check_policy_compliance",
            "reason": "The request depends on policy compliance for reimbursable expenses.",
        }

    return {
        "needs_tool": False,
        "tool_name": "none",
        "reason": "Retrieval is sufficient; no external tool action is required.",
    }
