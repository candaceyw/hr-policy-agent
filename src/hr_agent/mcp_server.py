from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from hr_agent.retrieval import retrieve


def _mock_data_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "mock_data"


def _load_json(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_mcp_server() -> FastMCP:
    """Create a small FastMCP server with the policy and HR tools needed for teaching."""
    server = FastMCP("hr-policy-agent")

    @server.tool()
    def search_policy_documents(query: str, k: int = 3) -> dict:
        """Search the HR policy corpus for relevant policy passages."""
        corpus_dir = Path(__file__).resolve().parents[2] / "corpus"
        results = retrieve(query, corpus_dir=corpus_dir, k=k)
        return {"results": results}

    @server.tool()
    def get_policy_section(doc_id: str, section: str | None = None) -> dict:
        """Return the matching policy section from a document."""
        corpus_dir = Path(__file__).resolve().parents[2] / "corpus"
        file_path = corpus_dir / f"{doc_id}.md"
        if not file_path.exists():
            return {"error": "not_found", "message": f"Document {doc_id} was not found."}

        text = file_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        section_lines: list[str] = []
        current_heading: str | None = None
        reading = section is None

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                heading = stripped.lstrip("# ").strip()
                if section is not None and current_heading is not None and heading == section:
                    reading = True
                    current_heading = heading
                elif section is not None and current_heading is not None and stripped.startswith("#"):
                    if reading:
                        break
                if section is None:
                    reading = True
                current_heading = heading
            if reading:
                section_lines.append(line)

        return {
            "doc_id": doc_id,
            "section": section or current_heading or "document",
            "content": "\n".join(section_lines).strip(),
        }

    @server.tool()
    def list_policy_documents() -> dict:
        """List available policy documents in the corpus."""
        corpus_dir = Path(__file__).resolve().parents[2] / "corpus"
        docs = sorted(str(path.name) for path in corpus_dir.glob("*.md"))
        return {"documents": docs}

    @server.tool()
    def check_policy_compliance(question: str) -> dict:
        """Return a minimal compliance assessment for an HR policy question."""
        lowered = question.lower()
        if "expense" in lowered or "reimbursement" in lowered:
            return {"status": "requires_review", "message": "Expense reimbursement requires policy review and a manager approval check."}
        if "pto" in lowered or "vacation" in lowered:
            return {"status": "ok", "message": "PTO is governed by the time-off policy and manager approval rules."}
        return {"status": "not_applicable", "message": "No direct compliance check is required for this question."}

    @server.tool()
    def lookup_employee_profile(employee_id: str) -> dict:
        """Look up a synthetic employee profile by employee id."""
        employees = _load_json(_mock_data_dir() / "employees.json")
        for item in employees:
            if item["employee_id"] == employee_id:
                return item
        return {"error": "not_found", "message": f"Employee {employee_id} was not found."}

    @server.tool()
    def check_pto_balance(employee_id: str) -> dict:
        """Return synthetic PTO accrual and remaining balance data for an employee."""
        balances = _load_json(_mock_data_dir() / "pto_balances.json")
        for item in balances:
            if item["employee_id"] == employee_id:
                return item
        return {"error": "not_found", "message": f"No PTO record exists for {employee_id}."}

    @server.tool()
    def lookup_benefits_status(employee_id: str) -> dict:
        """Return the synthetic benefits status for an employee."""
        benefits = _load_json(_mock_data_dir() / "benefits_elections.json")
        for item in benefits:
            if item["employee_id"] == employee_id:
                return item
        return {"error": "not_found", "message": f"No benefits record exists for {employee_id}."}

    @server.tool()
    def create_mock_hr_ticket(employee_id: str, issue: str) -> dict:
        """Create a mock HR ticket for workflow demonstration without touching real systems."""
        return {
            "ticket_id": "HR-1001",
            "employee_id": employee_id,
            "issue": issue,
            "status": "created",
            "note": "This is a mock action used for demo purposes only.",
        }

    @server.tool()
    def draft_hr_email(employee_id: str, topic: str) -> dict:
        """Draft a mock HR email for the employee and the given topic."""
        return {
            "employee_id": employee_id,
            "topic": topic,
            "draft": "Subject: HR Follow-Up\n\nHello,\n\nThank you for reaching out. We have opened a review of your request and will follow up with the relevant policy guidance and next steps.\n\nBest,\nHR Team",
        }

    return server
