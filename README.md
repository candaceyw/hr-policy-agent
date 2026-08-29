# HR Policy Agent

A grounded HR policy assistant that answers employee questions using a curated policy corpus and a layered retrieval-and-answer workflow.

## What this project does
- reads HR policy content from the `corpus/` directory
- retrieves the most relevant passages for a user question
- builds a grounded answer with citations
- routes policy questions through a lightweight orchestration layer
- exposes the backend through a FastAPI API
- presents the experience in a React frontend

## Architecture
- Backend: Python 3.12 + FastAPI
- Retrieval layer: keyword-based policy retrieval over markdown corpus files
- Orchestration: routing and workflow logic for grounded responses
- Frontend: React + Vite dashboard-style interface

## Project structure
- `src/hr_agent/` — backend logic for retrieval, routing, answering, and orchestration
- `src/hr_agent/web/` — FastAPI application and API endpoints
- `corpus/` — HR policy source documents
- `frontend/` — React app
- `tests/` — validation for ingestion, retrieval, routing, and API behavior

## Local setup

### 1) Create the Python environment
```bash
cd /Users/candacewilson/projects/hr-policy-agent
python3.12 -m venv .venv312
. .venv312/bin/activate
pip install .
```

### 2) Run the backend
```bash
cd /Users/candacewilson/projects/hr-policy-agent
. .venv312/bin/activate
PYTHONPATH=src python -m uvicorn hr_agent.web.app:app --host 0.0.0.0 --port 8000
```

### 3) Run the frontend
```bash
cd /Users/candacewilson/projects/hr-policy-agent/frontend
npm install
npm run dev -- --host 0.0.0.0
```

Then open the frontend at `http://localhost:5173`.

## Validation
```bash
cd /Users/candacewilson/projects/hr-policy-agent
. .venv312/bin/activate
PYTHONPATH=. python -m pytest -q
```

## Private notes
This repository intentionally keeps developer-only notes out of source control. Local notes such as `build-note.md` are ignored and remain private to the creator.
