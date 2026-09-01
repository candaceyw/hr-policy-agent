from hr_agent.directory import get_employee_name, resolve_employee


def test_resolve_by_employee_id():
    assert resolve_employee("How much PTO does E-1002 have?") == "E-1002"
    assert resolve_employee("show me e-1007 please") == "E-1007"


def test_resolve_by_full_name():
    assert resolve_employee("How much PTO does Marcus Silva have?") == "E-1002"
    assert resolve_employee("what is priya nair's benefits status") == "E-1003"


def test_resolve_by_partial_name_when_allowed():
    assert resolve_employee("does Marcus have any PTO left") == "E-1002"
    assert resolve_employee("look up Nair") == "E-1003"


def test_partial_name_ignored_for_routing():
    # "foster" is a common word and also a surname (Andre Foster, E-1013).
    assert resolve_employee("parental leave for a foster placement", allow_partial=False) is None
    assert resolve_employee("does Marcus have PTO", allow_partial=False) is None


def test_resolve_returns_none_when_no_reference():
    assert resolve_employee("How much PTO do employees accrue per month?") is None


def test_get_employee_name():
    assert get_employee_name("E-1002") == "Marcus Silva"
    assert get_employee_name("e-1002") == "Marcus Silva"
    assert get_employee_name("E-9999") is None
