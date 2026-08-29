# HR Policy Agent

This project implements an HR policy and operations assistant using a Python backend and a React frontend.

## Stack
- Python 3.12 backend
- FastAPI API server
- LangGraph orchestration layer
- MCP tooling model
- React + TypeScript frontend

## Corpus
The project ships with a small but coherent synthetic HR policy corpus under `corpus/`.

## Running locally

### Backend
```bash
uv sync
uv run uvicorn src.hr_agent.web.app:app --reload --host 0.0.0.0 --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

## Verification
```bash
uv run pytest
```
