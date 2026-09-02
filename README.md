# HR Policy Agent

[![CI](https://github.com/candaceyw/hr-policy-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/candaceyw/hr-policy-agent/actions/workflows/ci.yml)

A grounded HR policy assistant for the fictional **Northwind Robotics**. It
answers employee questions from a curated policy corpus (RAG), runs multi-step
workflows through an agent that calls **MCP tools** for employee data, stops for
confirmation before any action, and returns citations plus an operational trace
with every answer.

**Live:** https://web-production-1fa45.up.railway.app  ·  `/health`:
[`…/health`](https://web-production-1fa45.up.railway.app/health)

## What it does

- Retrieves the most relevant policy sections for a question (vector search over
  a committed `sqlite-vec` index, keyword TF-IDF fallback).
- Composes a short, **cited** answer grounded in those sections.
- Runs an agent loop that decides when to call a tool — PTO balance, benefits
  status, employee profile — and when RAG alone is enough.
- **Asks before acting:** filing a mock HR ticket or drafting an email stops at
  a confirmation gate.
- Routes ambiguous requests to one clarifying question and out-of-scope requests
  to a redirect, before any model call.
- Degrades to RAG-only (with a caveat in the trace) if the MCP service or the
  LLM is unavailable.

Two demo workflows run end-to-end from the UI presets: **remote-work
eligibility** (spans three policies + `lookup_employee_profile`) and **PTO
request** (`check_pto_balance` + policy + a confirmation-gated ticket).

## Architecture (short version)

```
React SPA ──POST /chat──► FastAPI (service "web")
                             │  in-memory session history
                             ▼
                          LangGraph agent
                          classify → [clarify | scope | agent ⇄ tools] → compose
                             │  MCP Streamable HTTP (private network)
                             ▼
                          FastMCP server (service "mcp") — 9 tools
                          ├─ sqlite-vec index  (read-only, committed)
                          └─ mock_data/*.json  (read-only)
```

- Python 3.12 + FastAPI; LangGraph orchestration; FastMCP tool server.
- Multi-provider LLM behind one file (`llm.py`); production runs Groq
  `qwen/qwen3.8-27b`. Embeddings on Gemini.
- React + Vite SPA, served by the backend in production.
- Full design write-up (data model, API, agent graph, tests, deployment,
  evaluation): [`design-and-evaluation.md`](design-and-evaluation.md).

## Repository layout

| Path | Contents |
| --- | --- |
| `src/hr_agent/` | backend: `retrieval`, `answering`, `agent/` (graph + gate), `mcp_client/`, `mcp_server.py`, `ingest/`, `web/` |
| `corpus/` | 17 HR policy documents (~40 pages) in 4 formats: 13 Markdown, 2 PDF, 1 HTML, 1 text |
| `corpus-facts.md` | internal reference — every figure in the corpus, kept consistent with `mock_data/` |
| `mock_data/` | synthetic employees, PTO balances, benefits, offices, tickets |
| `data/index/` | committed `sqlite-vec` index + `manifest.json` (hash-verified in CI) |
| `evaluation/` | 25-item gold set, metrics, LLM judge, runner, ablation, `RESULTS.md` |
| `frontend/` | React + Vite SPA |
| `tests/` | 139 tests — ingestion, retrieval, gate, agent loop, MCP, app, evaluation |
| `scripts/` | `build_index.py` (`--verify`), `build_corpus_formats.py` |

> **MCP server & tool definitions:** [`src/hr_agent/mcp_server.py`](src/hr_agent/mcp_server.py) — the `FastMCP` server and all 9 tool schemas are defined inline in `build_mcp_server()`. The agent-side MCP client (discovery, health, degrade-to-RAG) is in [`src/hr_agent/mcp_client/`](src/hr_agent/mcp_client/).

## Local setup

Python 3.12. From the repo root:

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e .

cp .env.example .env      # then set GEMINI_API_KEY (embeddings) and GROQ_API_KEY (generation)
```

Run the backend (spawns the MCP server over stdio when `MCP_SERVER_URL` is unset):

```bash
python -m uvicorn hr_agent.web.app:app --host 0.0.0.0 --port 8000
```

Run the frontend (dev):

```bash
cd frontend && npm install && npm run dev -- --host 0.0.0.0   # http://localhost:5173
```

The committed index is already valid — rebuild only after changing the corpus or
chunking config: `python scripts/build_index.py`.

For the production-shaped two-process / two-container setup, see
[`deployed.md`](deployed.md).

## Tests & checks

```bash
python -m pytest -q                       # 139 tests, offline by default
ruff check .                              # lint (line length 100)
python scripts/build_index.py --verify    # index is deterministic vs the manifest
python -m evaluation.run_eval --smoke --offline   # eval harness plumbing, no tokens
```

## CI/CD

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push and PR:

- **test** — install pinned `requirements.txt` (the set the Docker image ships)
  → import/start check → `ruff check` → index-determinism verify → full `pytest`
  (incl. MCP discovery + a tool call, app start via `TestClient` + lifespan) →
  offline evaluation smoke subset.
- **frontend** — `npm ci && npm run build`.

Both Railway services are set to **Wait for CI**, so a red run cannot deploy.

## Evaluation

25 items across five categories (straightforward, multi-doc, tool-requiring,
ambiguous, out-of-scope), each with gold `doc_id`s, expected tools, and expected
behavior. Metrics: groundedness (LLM judge), citation P/R/F1, tool-selection
Jaccard, workflow completion, escalation/clarification accuracy, action-safety,
latency p50/p95, plus a retrieval-`k` ablation.

```bash
python -m evaluation.run_eval                          # full judged run + RESULTS.md
python -m evaluation.run_eval --only straightforward,multi_doc   # citation-bearing subset
python -m evaluation.run_eval --rejudge results/<f>.json   # re-score saved answers only
python -m evaluation.ablation --no-judge               # k sweep + tools-vs-RAG
```

Latest results and analysis: [`evaluation/RESULTS.md`](evaluation/RESULTS.md)
and [`design-and-evaluation.md`](design-and-evaluation.md) §7. CI runs the
offline smoke subset; the full judged run is executed locally and committed.

## Documentation

| Doc | Purpose |
| --- | --- |
| [`design-and-evaluation.md`](design-and-evaluation.md) | architecture, data, API, implementation, testing, deployment, evaluation |
| [`deployed.md`](deployed.md) | Railway two-service setup + first-deploy gotchas |
| [`ai-tooling.md`](ai-tooling.md) | how AI tooling was used to build this, and the checks against AI error |

## Private notes

`build-note.md` is a git-ignored developer learning log and is not part of the
repository.
