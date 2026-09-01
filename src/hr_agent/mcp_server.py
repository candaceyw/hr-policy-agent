from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from hr_agent.config import settings
from hr_agent.retrieval import load_corpus_documents, load_sections, retrieve

logger = logging.getLogger(__name__)

_HTTP_TRANSPORT = "streamable-http"
_HTTP_ALIASES = {"http", "streamable-http", "streamable_http"}


def _mock_data_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "mock_data"


def _load_json(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _employee_name(employee_id: str) -> str | None:
    for item in _load_json(_mock_data_dir() / "employees.json"):
        if item["employee_id"] == employee_id:
            return item.get("name")
    return None


def _ticket_category(issue: str) -> str:
    lowered = issue.lower()
    if any(w in lowered for w in ("laptop", "monitor", "equipment", "device", "hardware", "chair")):
        return "equipment"
    if any(w in lowered for w in ("pto", "vacation", "leave", "time off", "time-off")):
        return "pto"
    if any(w in lowered for w in ("benefit", "enrollment", "coverage", "insurance", "401")):
        return "benefits"
    if any(w in lowered for w in ("pay", "payroll", "salary", "paycheck", "reimburs", "expense")):
        return "payroll"
    return "general"


def build_mcp_server(host: str | None = None, port: int | None = None) -> FastMCP:
    """Create a small FastMCP server with the policy and HR tools needed for teaching.

    ``host`` / ``port`` only matter when the server is run over Streamable HTTP;
    they default to the values in :mod:`hr_agent.config`.
    """
    server = FastMCP(
        "hr-policy-agent",
        host=host or settings.mcp_host,
        port=port if port is not None else settings.mcp_port,
    )

    @server.tool()
    def search_policy_documents(query: str, k: int = 3) -> dict:
        """Search the HR policy corpus for relevant policy passages."""
        corpus_dir = Path(__file__).resolve().parents[2] / "corpus"
        results = retrieve(query, corpus_dir=corpus_dir, k=k)
        return {"results": results}

    @server.tool()
    def get_policy_section(doc_id: str, section: str | None = None) -> dict:
        """Return the matching policy section from a document (any supported format)."""
        corpus_dir = Path(__file__).resolve().parents[2] / "corpus"
        matches = [d for d in load_corpus_documents(corpus_dir) if d.stem == doc_id]
        if not matches:
            return {"error": "not_found", "message": f"Document {doc_id} was not found."}

        sections = load_sections(matches[0])
        if section is None:
            content = "\n\n".join(f"{title}\n{body}" for title, body in sections)
            return {"doc_id": doc_id, "section": "document", "content": content.strip()}

        wanted = section.strip().lower()
        for title, body in sections:
            if title.strip().lower() == wanted:
                return {"doc_id": doc_id, "section": title, "content": body.strip()}
        return {
            "error": "not_found",
            "message": f"Section '{section}' was not found in {doc_id}.",
        }

    @server.tool()
    def list_policy_documents() -> dict:
        """List available policy documents in the corpus as ``{doc_id, title}`` pairs."""
        corpus_dir = Path(__file__).resolve().parents[2] / "corpus"
        docs = [
            {"doc_id": path.stem, "title": path.stem.replace("-", " ").title()}
            for path in load_corpus_documents(corpus_dir)
        ]
        return {"documents": docs}

    @server.tool()
    def check_policy_compliance(question: str) -> dict:
        """Advisory compliance check for an HR scenario, backed by policy retrieval.

        Retrieves the most relevant policy sections and returns them as
        ``relevant_sections`` evidence alongside a heuristic ``status``:

        * ``requires_review`` -- the scenario touches an area that policy routes
          through manager / People Ops approval (relocation and out-of-state or
          international remote work, expenses and reimbursement, leaves of
          absence, terminations, grievances).
        * ``ok`` -- routine time-off (PTO, vacation, holidays, sick leave).
        * ``not_applicable`` -- no review trigger matched, or the corpus does
          not cover the question.

        This is a hint for the agent, not an authoritative ruling; the cited
        sections are the substance.
        """
        corpus_dir = Path(__file__).resolve().parents[2] / "corpus"
        passages = retrieve(question, corpus_dir=corpus_dir, k=3)
        relevant_sections = [
            {"doc_id": p["doc_id"], "section": p["section"], "snippet": p["snippet"]}
            for p in passages
        ]

        lowered = question.lower()
        review_triggers = (
            "expense", "reimburse", "reimbursement", "receipt",
            "relocat", "another state", "out of state", "out-of-state",
            "international", "abroad", "overseas", "visa", "tax residency",
            "leave of absence", "fmla", "sabbatical",
            "terminat", "resignation", "grievance", "harassment", "misconduct",
        )
        routine_triggers = ("pto", "vacation", "holiday", "time off", "sick leave", "bereavement")

        if any(term in lowered for term in review_triggers):
            status = "requires_review"
            message = (
                "This scenario falls in an area policy routes through manager and "
                "People Ops review. Confirm against the cited sections before acting."
            )
        elif any(term in lowered for term in routine_triggers):
            status = "ok"
            message = (
                "Routine time-off request governed by the time-off policy and "
                "standard manager approval. See the cited sections."
            )
        elif relevant_sections:
            status = "not_applicable"
            message = (
                "No explicit review trigger matched. The cited sections are the "
                "closest policy coverage; use them to answer directly."
            )
        else:
            status = "not_applicable"
            message = "This question does not appear to be covered by the indexed HR policy corpus."

        return {
            "question": question,
            "status": status,
            "message": message,
            "relevant_sections": relevant_sections,
        }

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
        """Return synthetic PTO accrual and remaining balance data for an employee.

        Includes a derived ``available_hours`` (accrued - used - pending) so the
        agent never has to do the arithmetic itself.
        """
        balances = _load_json(_mock_data_dir() / "pto_balances.json")
        for item in balances:
            if item["employee_id"] == employee_id:
                available = (
                    item.get("accrued_hours", 0.0)
                    - item.get("used_hours", 0.0)
                    - item.get("pending_hours", 0.0)
                )
                return {**item, "available_hours": round(available, 2)}
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
        """Create a mock HR ticket for workflow demonstration without touching real systems.

        The ticket id is a deterministic ``HR-<hash>`` of ``(employee_id, issue)``
        so the same request always yields the same id. The shape matches the
        ``mock_data/hr_tickets.json`` sample rows; nothing is persisted.
        """
        digest = hashlib.sha1(f"{employee_id}|{issue}".encode()).hexdigest()[:6].upper()
        summary = " ".join(issue.strip().split())
        if len(summary) > 80:
            summary = summary[:77].rstrip() + "..."
        return {
            "ticket_id": f"HR-{digest}",
            "employee_id": employee_id,
            "category": _ticket_category(issue),
            "summary": summary or "HR request",
            "details": issue.strip(),
            "status": "created_mock",
            "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "note": "Mock action for demo purposes only; no real HR system was touched.",
        }

    @server.tool()
    def draft_hr_email(employee_id: str, topic: str) -> dict:
        """Draft a mock HR email addressed to the employee about the given topic."""
        name = _employee_name(employee_id)
        greeting = f"Hi {name.split()[0]}," if name else "Hi there,"
        topic_clean = " ".join(topic.strip().split()) or "your request"
        draft = (
            f"Subject: HR follow-up: {topic_clean}\n\n"
            f"{greeting}\n\n"
            f"Thanks for reaching out about {topic_clean}. I've noted your request "
            f"(employee {employee_id}) and reviewed the relevant Northwind Robotics "
            f"policy. I'll follow up with the specific guidance and any approval steps "
            f"you need to complete.\n\n"
            f"If anything is time-sensitive, reply here and I'll prioritise it.\n\n"
            f"Best,\nNorthwind Robotics People Ops"
        )
        return {"employee_id": employee_id, "topic": topic_clean, "draft": draft}

    return server


def resolve_transport(http_flag: bool, configured: str | None = None) -> str:
    """Pick the MCP transport: stdio by default, Streamable HTTP when opted in.

    ``http_flag`` is the ``--http`` CLI switch (what the deploy command uses);
    ``configured`` is ``MCP_TRANSPORT`` from the environment. Either one enables HTTP.
    """
    configured = settings.mcp_transport if configured is None else configured
    if http_flag or configured.strip().lower() in _HTTP_ALIASES:
        return _HTTP_TRANSPORT
    return "stdio"


def main(argv: list[str] | None = None) -> None:
    """Entrypoint for ``python -m hr_agent.mcp_server``.

    No args => stdio (the web app spawns this as a child process).
    ``--http`` => a standalone Streamable HTTP service. Bind host/port come from
    ``--host``/``--port``, else ``$PORT`` (Railway/Render inject this), else
    ``MCP_HOST``/``MCP_PORT``. In HTTP mode the host defaults to ``0.0.0.0`` so
    the service is reachable inside a container.
    """
    parser = argparse.ArgumentParser(description="Run the HR policy MCP server.")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Serve over Streamable HTTP instead of stdio.",
    )
    parser.add_argument("--host", default=None, help="Bind host for HTTP (default: 0.0.0.0).")
    parser.add_argument(
        "--port", type=int, default=None, help="Bind port for HTTP (default: $PORT or MCP_PORT)."
    )
    args = parser.parse_args(argv)

    transport = resolve_transport(args.http)
    host = args.host
    port = args.port or (int(os.environ["PORT"]) if os.environ.get("PORT") else None)
    if transport == _HTTP_TRANSPORT and host is None:
        # a container service must bind all interfaces
        host = "0.0.0.0"
    server = build_mcp_server(host=host, port=port)

    if transport == _HTTP_TRANSPORT:
        # stdio mode must keep stdout clean for the protocol; only log for HTTP.
        logging.basicConfig(level=logging.INFO)
        logger.info(
            "Starting MCP server over Streamable HTTP on %s:%s%s",
            server.settings.host,
            server.settings.port,
            server.settings.streamable_http_path,
        )

    server.run(transport=transport)


if __name__ == "__main__":
    main()
