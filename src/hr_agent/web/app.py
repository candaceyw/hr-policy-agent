from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

from hr_agent.answering import build_grounded_answer

app = FastAPI(title="HR Policy Agent")


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
    corpus_dir = project_root / "corpus"
    answer_data = build_grounded_answer(request.message, corpus_dir=corpus_dir, k=3)

    return {
        "answer": answer_data["answer"],
        "citations": answer_data["citations"],
        "trace": answer_data["trace"],
        "escalation": False,
    }
