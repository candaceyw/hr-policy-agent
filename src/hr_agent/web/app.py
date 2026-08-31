from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from hr_agent.config import settings
from hr_agent.ingest.indexer import load_manifest
from hr_agent.llm import embedding_available
from hr_agent.mcp_client import discovery
from hr_agent.orchestration import arun_chat
from hr_agent.vector_store import DEFAULT_INDEX_PATH, index_exists
from hr_agent.web.sessions import SessionStore

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Discover MCP tools once at startup; degrade to RAG-only if that fails.

    Tool discovery spawns a subprocess (stdio) or opens an HTTP session, so it
    belongs in startup, not import or per-request. Results live on ``app.state``.
    """
    app.state.mcp_ready = False
    app.state.tools_discovered = 0
    app.state.mcp_transport = discovery.active_transport()
    app.state.agent_tools = []
    app.state.sessions = SessionStore()
    # Injectable model seam: tests set this to a scripted fake; None => real provider.
    if not hasattr(app.state, "chat_model"):
        app.state.chat_model = None
    try:
        tools = await discovery.get_tools_async()
        app.state.agent_tools = tools
        app.state.tools_discovered = len(tools)
        app.state.mcp_ready = True
        logger.info(
            "MCP ready: %d tools over %s", len(tools), app.state.mcp_transport
        )
    except Exception:
        logger.exception("MCP tool discovery failed at startup; serving RAG-only")
    yield
    # langchain-mcp-adapters opens a fresh session per call -- nothing to close.


app = FastAPI(title="HR Policy Agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174", "http://127.0.0.1:5173", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    employee_id: str | None = None
    confirm: bool | None = None
    session_id: str | None = None


# Live MCP probe, cached briefly so /health polling and each /chat don't re-probe
# on every hit. A probe re-runs tool discovery, so it reflects the MCP service
# going down *after* startup (the two-service degradation demo).
_MCP_PROBE_TTL = 15.0
_mcp_probe: dict = {"at": 0.0, "value": None}


def _mcp_status() -> dict:
    now = time.monotonic()
    if _mcp_probe["value"] is None or now - _mcp_probe["at"] > _MCP_PROBE_TTL:
        _mcp_probe["value"] = discovery.health()
        _mcp_probe["at"] = now
    return _mcp_probe["value"]


@app.get("/health")
def health() -> dict:
    has_index = index_exists()
    chunks = 0
    if has_index:
        try:
            chunks = int(load_manifest(DEFAULT_INDEX_PATH).get("chunk_count", 0))
        except (OSError, ValueError):
            chunks = 0
    active = "vector" if (has_index and embedding_available()) else "keyword"
    mcp = _mcp_status()
    return {
        "status": "ok",
        "mcp": {
            "connected": bool(mcp.get("connected")),
            "tools_discovered": int(mcp.get("tools_discovered", 0)),
            "transport": mcp.get("transport", discovery.active_transport()),
        },
        "vector_store": {
            "index_present": has_index,
            "chunks": chunks,
            "embedding_model": settings.embedding_model,
            "embedding_key_configured": embedding_available(),
        },
        "retrieval": {"active_method": active},
    }


@app.post("/chat")
async def chat(request: ChatRequest) -> dict:
    project_root = Path(__file__).resolve().parents[3]
    corpus_dir = str(project_root / "corpus")
    tools = list(getattr(app.state, "agent_tools", []) or [])
    model = getattr(app.state, "chat_model", None)

    store: SessionStore = getattr(app.state, "sessions", None) or SessionStore()
    session_id, session = store.get(request.session_id)
    employee_id = request.employee_id or session.employee_id

    workflow_result = await arun_chat(
        request.message,
        tools,
        confirm=request.confirm,
        corpus_dir=corpus_dir,
        model=model,
        employee_id=employee_id,
        history=list(session.history),
    )

    # A pending confirmation is not a finished turn -- record it only once it
    # resolves (on the follow-up request that carries `confirm`).
    if not workflow_result.get("pending_action"):
        store.record_turn(
            session_id,
            query=request.message,
            answer=workflow_result.get("answer", ""),
            employee_id=workflow_result.get("employee_id"),
        )

    return {
        "session_id": session_id,
        "answer": workflow_result.get("answer", "I could not determine an answer."),
        "citations": workflow_result.get("citations", []),
        "trace": workflow_result.get("trace", []),
        "escalation": bool(workflow_result.get("escalation", False)),
        "pending_action": workflow_result.get("pending_action"),
        "llm_error": workflow_result.get("llm_error"),
        "intent": workflow_result.get("intent", ""),
    }


# Serve the built SPA (production single-container). Mounted last so it only
# catches paths the API routes above did not. In dev the SPA is served by Vite,
# so this is skipped when there is no build on disk.
_static_dir = (
    Path(settings.static_dir)
    if settings.static_dir
    else Path(__file__).resolve().parents[3] / "frontend" / "dist"
)
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="spa")
    logger.info("Serving SPA from %s", _static_dir)
else:
    logger.info("No SPA build at %s; API-only (Vite serves the UI in dev)", _static_dir)
