from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_EMPLOYEE_ID_RE = re.compile(r"\bE-\d+\b", re.IGNORECASE)


def _mock_data_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "mock_data"


@lru_cache(maxsize=1)
def load_employees() -> tuple[dict[str, str], ...]:
    """Load the synthetic employee directory (employee_id + name)."""
    path = _mock_data_dir() / "employees.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    return tuple({"employee_id": r["employee_id"], "name": r["name"]} for r in records)


def extract_employee_id(text: str) -> str | None:
    """Return the first ``E-1234`` style id in the text, upper-cased."""
    match = _EMPLOYEE_ID_RE.search(text)
    return match.group(0).upper() if match else None


def get_employee_name(employee_id: str) -> str | None:
    eid = employee_id.upper()
    for employee in load_employees():
        if employee["employee_id"].upper() == eid:
            return employee["name"]
    return None


def resolve_employee(text: str, *, allow_partial: bool = True) -> str | None:
    """Return an employee_id referenced in free text, by id or by name.

    Resolution order: an ``E-1234`` id, then a full name ("Marcus Silva"), then
    (only when ``allow_partial``) a unique first or last name as a whole word
    ("Marcus" or "Silva"). Returns None when nothing matches or the reference is
    ambiguous. Routing uses ``allow_partial=False`` so a common word that happens
    to be a surname (for example "foster") does not look like an employee.
    """
    direct = extract_employee_id(text)
    if direct is not None:
        return direct

    lowered = text.lower()
    employees = load_employees()

    full = {e["employee_id"] for e in employees if e["name"].lower() in lowered}
    if len(full) == 1:
        return next(iter(full))
    if len(full) > 1:
        return None

    if not allow_partial:
        return None

    partial: set[str] = set()
    for employee in employees:
        for part in employee["name"].lower().split():
            if re.search(rf"\b{re.escape(part)}\b", lowered):
                partial.add(employee["employee_id"])
                break
    return next(iter(partial)) if len(partial) == 1 else None
