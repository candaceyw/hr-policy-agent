from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from hr_agent.answering import build_grounded_answer
from hr_agent.orchestration import run_workflow

app = FastAPI(title="HR Policy Agent")
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


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "mcp": {"connected": False, "tools_discovered": 0},
        "vector_store": {"loaded": True, "chunks": 12},
    }


@app.post("/chat")
def chat(request: ChatRequest) -> dict:
    project_root = Path(__file__).resolve().parents[3]
    corpus_dir = str(project_root / "corpus")
    workflow_result = run_workflow(request.message, corpus_dir=corpus_dir)

    return {
        "answer": workflow_result.get("answer", "I could not determine an answer."),
        "citations": workflow_result.get("citations", []),
        "trace": workflow_result.get("trace", []),
        "escalation": False,
    }
