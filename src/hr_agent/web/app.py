from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from hr_agent.config import settings
from hr_agent.ingest.indexer import load_manifest
from hr_agent.llm import embedding_available
from hr_agent.mcp_client import discovery
from hr_agent.orchestration import arun_chat
from hr_agent.vector_store import DEFAULT_INDEX_PATH, index_exists

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
    return {
        "status": "ok",
        "mcp": {
            "connected": bool(getattr(app.state, "mcp_ready", False)),
            "tools_discovered": int(getattr(app.state, "tools_discovered", 0)),
            "transport": getattr(app.state, "mcp_transport", discovery.active_transport()),
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
    workflow_result = await arun_chat(
        request.message,
        tools,
        confirm=request.confirm,
        corpus_dir=corpus_dir,
        model=model,
        employee_id=request.employee_id,
    )

    return {
        "answer": workflow_result.get("answer", "I could not determine an answer."),
        "citations": workflow_result.get("citations", []),
        "trace": workflow_result.get("trace", []),
        "escalation": bool(workflow_result.get("escalation", False)),
        "pending_action": workflow_result.get("pending_action"),
        "llm_error": workflow_result.get("llm_error"),
        "intent": workflow_result.get("intent", ""),
    }
