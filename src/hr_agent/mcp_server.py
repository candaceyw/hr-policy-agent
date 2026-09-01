from __future__ import annotations

import argparse
import json
import logging
import os
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
        """List available policy documents in the corpus."""
        corpus_dir = Path(__file__).resolve().parents[2] / "corpus"
        docs = [path.name for path in load_corpus_documents(corpus_dir)]
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
