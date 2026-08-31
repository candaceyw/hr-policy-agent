# HR Policy Agent

[![CI](https://github.com/candaceyw/hr-policy-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/candaceyw/hr-policy-agent/actions/workflows/ci.yml)

A grounded HR policy assistant that answers employee questions using a curated policy corpus and a layered retrieval-and-answer workflow.

**Live:** https://web-production-1fa45.up.railway.app — deployment details in [`deployed.md`](deployed.md).

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
- `corpus/` — HR policy source documents (17 documents, ~40 pages) for the
  fictional Northwind Robotics, in four formats: Markdown (13), PDF (2), HTML (1),
  and plain text (1)
- `corpus-facts.md` — internal reference listing every concrete figure used across
  the corpus, kept consistent with `mock_data/`
- `scripts/build_corpus_formats.py` — regenerates the PDF/HTML renditions from
  their Markdown sources
- `mock_data/` — synthetic employee, PTO, benefits, office, and ticket data
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

## Tests

```bash
cd /Users/candacewilson/projects/hr-policy-agent
. .venv312/bin/activate
PYTHONPATH=. python -m pytest -q          # full suite, offline by default
ruff check .                             # lint
python scripts/build_index.py --verify   # vector index matches the corpus
```

## CI/CD

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push and
pull request:

- **test** job — installs the pinned `requirements.txt` (the same set the Docker
  image ships), runs an import/start check on the FastAPI app, `ruff check`, the
  index-determinism verify, then the full `pytest` suite. The suite starts the
  app via `TestClient` + lifespan and exercises MCP tool discovery and an MCP
  tool call ([`tests/test_app.py`](tests/test_app.py),
  [`tests/test_mcp.py`](tests/test_mcp.py)).
- **frontend** job — `npm ci && npm run build` for the Vite SPA.

Both Railway services are set to **Wait for CI**, so a red run blocks the
deploy. See [`deployed.md`](deployed.md).

## Deployment

Two Railway services (`web`, `mcp`) built from one `Dockerfile`. Full setup,
environment variables, and cold-start notes: [`deployed.md`](deployed.md).

## Evaluation

The evaluation harness lands in `evaluation/` — the question/gold set, the
runner, and reported results (groundedness, citation accuracy, tool-selection
accuracy, workflow completion, safety, latency p50/p95, plus a retrieval
ablation). Run it with `python -m evaluation.run` once present.

## Private notes
This repository intentionally keeps developer-only notes out of source control. Local notes such as `build-note.md` are ignored and remain private to the creator.
