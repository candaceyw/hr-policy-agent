# Design & Evaluation — HR Policy Agent

Northwind Robotics HR policy assistant: grounded RAG over a curated policy
corpus, a LangGraph agent that selects MCP tools, a confirmation gate before any
action, and an operational trace on every answer.

- **Live:** https://web-production-1fa45.up.railway.app
- **Code map:** `README.md`; **deploy:** `deployed.md`; **AI tooling:** `ai-tooling.md`
- **Raw eval output:** `evaluation/RESULTS.md`, `evaluation/results/*.json`

---

## 1. Architecture

```
React SPA (Vite)
   │  POST /chat        { message, employee_id?, session_id?, confirm? }
   │  GET  /health
   ▼
FastAPI  (Railway service "web")
   │  in-memory SessionStore  (history + learned employee_id, keyed by session_id)
   ▼
LangGraph agent graph
   classify_intent ──► clarify           (missing/unknown employee, or too vague)
        │          ──► guardrail_scope   (out-of-corpus policy question)
        ▼
      agent ◄────────► tools (ToolNode over MCP-discovered tools)
        │  destructive tool call ──► confirm_gate ──► (pending_action, stop)
        │                                         └─► declined  (confirm=false)
        ▼
      compose ──► answer + citations + trace
   │  MCP Streamable HTTP  (Railway private network)
   ▼
FastMCP server  (Railway service "mcp")  — 9 tools
   ├─ sqlite-vec index  data/index/index.sqlite   (read-only, committed)
   └─ mock_data/*.json                            (read-only; tickets in-process only)

Build-time (local + CI):
   corpus/*.{md,pdf,html,txt} ─► load → clean → heading-aware chunk → embed → index
                              ─► data/index/index.sqlite  (deterministic, committed, CI-verified)
```

### Layers and why they are separate

| Layer | Module | Responsibility |
| --- | --- | --- |
| Web / API | `web/app.py`, `web/sessions.py` | HTTP, session history, `/health` |
| Orchestration | `agent/graph.py`, `agent/gate.py`, `orchestration.py` | route → tool loop → compose; degrade to RAG-only |
| MCP client | `mcp_client/discovery.py` | runtime tool discovery; stdio or Streamable HTTP |
| MCP server | `mcp_server.py` | the 9 tools; typed results, never raises across the wire |
| Retrieval | `retrieval.py`, `vector_store.py` | `retrieve_passages` is vector-first (sqlite-vec) with a keyword TF-IDF fallback; the `search_policy_documents` MCP tool uses the keyword retriever directly |
| Ingestion | `ingest/` | deterministic corpus → chunks → embeddings → index |
| Answering | `answering.py` | grounded synthesis for the RAG-only path |
| LLM | `llm.py` | **the only file importing a model SDK**; provider is one config switch |
| Config | `config.py` | every env-backed setting; no hard-coded model/port/k/size |

Key patterns: **provider isolation** (swap Gemini↔Groq with one env var),
**transport abstraction** (MCP over stdio locally, Streamable HTTP in prod),
**human-in-the-loop** (a two-call `pending_action` handshake before any mock
action), **graceful degradation** (MCP down or no LLM key ⇒ RAG-only answer with
a caveat in the trace).

### The agent graph

`classify_intent` is **deterministic — no LLM call**. Three cheap signals:
employee resolution (a person-specific request that names nobody → `clarify`),
an ambiguity regex (`"Am I eligible?"` → `clarify`), and the vector-retrieval
scope score (a policy question the corpus does not cover → `guardrail_scope`).
Everything else enters the `agent` ↔ `tools` loop, which is an LLM binding the
MCP tools and choosing calls, bounded by `MAX_TOOL_ITERATIONS`. A `nudge` node
recovers a model that stops early with filler instead of an answer. `compose`
takes the last model message as the answer and attaches deduped citations.

The **trace** stores only operational fields — `step`, `type`, `name`,
`args_summary`, `result_summary` — never model chain-of-thought.

---

## 2. Data

### Policy corpus (`corpus/`, the source of truth)

17 documents (~40 pages) for the fictional Northwind Robotics, in **four
formats** to exercise the loaders: 13 Markdown, 2 PDF (`06`, `09`), 1 HTML
(`12`), 1 plain text (`17`). `corpus-facts.md` is an internal reference listing
every concrete figure so the documents stay mutually consistent and consistent
with `mock_data/`. `scripts/build_corpus_formats.py` regenerates the PDF/HTML
renditions from Markdown.

### Vector index (`data/index/index.sqlite`, committed)

| | |
| --- | --- |
| Chunks | 232 |
| Chunk size / overlap | 800 / 120 tokens (tiktoken count) |
| Embeddings | `gemini-embedding-001`, 768-dim, L2-normalised |
| Store | `sqlite-vec` virtual table + a companion `chunks` table |
| Manifest | `data/index/manifest.json` — chunk count, SHA-256 of concatenated chunk text, size/overlap, model, build time |

Chunking is **heading-aware and pure**: walk the heading tree, pack sentences
into token windows within each leaf section, never split a sentence, carry the
`section_path` breadcrumb. Identical input + config ⇒ byte-identical chunks.
`scripts/build_index.py --verify` rebuilds to a temp file and compares the
content hash; CI runs it on every push.

### Structured mock data (`mock_data/*.json`, read-only)

`employees.json` (14 people, E-1001…E-1014), `pto_balances.json`,
`benefits_elections.json`, `office_locations.json`, `hr_tickets.json`.
`create_mock_hr_ticket` appends only to an in-process list — the committed
`hr_tickets.json` is never mutated.

### Sessions

In-memory `SessionStore` in the `web` service, keyed by `session_id`: message
history plus a learned `employee_id`. Not persisted.

---

## 3. API

### `POST /chat`

Request `{ message, employee_id?, session_id?, confirm? }` → response:

```json
{
  "session_id": "…",
  "answer": "…",
  "citations": [ { "doc_id", "title", "section", "snippet" } ],
  "trace": [ { "step", "type", "name", "args_summary", "result_summary" } ],
  "escalation": false,
  "pending_action": { "tool", "args_summary", "description" } | null,
  "intent": "policy_qa | agentic_workflow | clarify | out_of_scope | …",
  "llm_error": null
}
```

When `pending_action` is present the client re-POSTs with the same `session_id`
and `confirm: true` (execute) or `confirm: false` (decline). A pending turn is
**not** recorded in history until it resolves.

### `GET /health`

```json
{
  "status": "ok",
  "mcp":  { "connected": true, "tools_discovered": 9, "transport": "streamable_http" },
  "vector_store": { "index_present": true, "chunks": 232,
                    "embedding_model": "gemini-embedding-001", "embedding_key_configured": true },
  "retrieval": { "active_method": "vector" }
}
```

`/health` live-probes the MCP service on a 15 s TTL, so stopping `mcp` in Railway
is a visible degradation demo within ~15 s.

### MCP tools (discovered, not REST)

| Tool | Purpose | Notes |
| --- | --- | --- |
| `search_policy_documents(query, k=3)` | top-k policy passages (keyword TF-IDF) | primary grounding path |
| `get_policy_section(doc_id, section?)` | full section text | exact section match |
| `list_policy_documents()` | doc catalogue | |
| `check_policy_compliance(question)` | keyword heuristic → `ok` / `requires_review` / `not_applicable` | lightweight hint, not authoritative |
| `lookup_employee_profile(employee_id)` | Employee record | typed `not_found` |
| `check_pto_balance(employee_id)` | PTO record + derived `available_hours` | |
| `lookup_benefits_status(employee_id)` | BenefitsElection record | |
| `create_mock_hr_ticket(employee_id, issue)` | **gated** mock ticket | confirmation required |
| `draft_hr_email(employee_id, topic)` | **gated** mock email draft | never sends |

Every tool returns a typed object or `{ "error": "<code>", "message": "…" }` —
errors are never raised across the MCP boundary.

---

## 4. Implementation notes

- **Multi-provider LLM.** `LLM_PROVIDER` ∈ `gemini | groq | openai_compatible`.
  `llm.py` is the only SDK importer; it exposes `chat_model()` (a LangChain
  `BaseChatModel` for the tool-calling loop), `generate_answer()` (string path
  for the RAG-only fallback), `embed()` (always Gemini, separate quota), and
  `judge_complete()` (evaluation only). Production runs Groq `qwen/qwen3.8-27b`.
- **Confirmation gate.** Implemented as a two-call `pending_action` handshake
  (not LangGraph `interrupt_before` + a checkpointer) because `/chat` keeps
  session state itself. Same guarantee: no mock action runs without an explicit
  `confirm: true`.
- **Determinism.** Chunking is pure; anything that samples uses `SEED` from
  config. The index is a committed artifact with a hash manifest, rebuilt and
  verified in CI.
- **Degradation.** `arun_chat` wraps the agent loop: no tools (MCP unreachable)
  or no LLM key ⇒ `generate_final_answer` from retrieval alone, with a
  `degradation` entry appended to the trace.

---

## 5. Testing

**116 tests, `ruff` clean, offline by default** (an autouse fixture forces the
no-LLM path; tests that need tool-calling inject a `ScriptedChatModel`).

| Area | Files | Count |
| --- | --- | --- |
| Ingestion / chunker | `test_ingestion.py`, `test_chunker.py` | 8 |
| Retrieval / guardrails | `test_retrieval.py`, `test_guardrails.py` | 9 |
| Routing / gate / directory | `test_routing.py`, `test_gate.py`, `test_directory.py` | 25 |
| Agent loop / orchestration / workflows | `test_agent_loop.py`, `test_orchestration.py`, `test_workflows.py` | 19 |
| MCP discovery + tool calls | `test_mcp.py` | 12 |
| App (`TestClient` + lifespan, `/chat`, `/health`) | `test_app.py` | 9 |
| Sessions / answering / LLM / embeddings | `test_sessions.py`, `test_answering.py`, `test_llm.py`, `test_embeddings.py` | 18 |
| Evaluation harness (incl. offline smoke) | `test_evaluation.py` | 16 |

CI (`.github/workflows/ci.yml`, on push + PR): install pinned `requirements.txt`
→ import/start check → `ruff check` → `build_index.py --verify` → full `pytest`
→ `run_eval --smoke --offline` (zero tokens) → SPA `npm run build`. Both Railway
services are set to **Wait for CI**, so a red run cannot ship.

---

## 6. Deployment

Two Railway services from **one repo and one `Dockerfile`**, differing only in
the start command:

| Service | Start command | Exposure |
| --- | --- | --- |
| `web` | *(Dockerfile default)* `uvicorn hr_agent.web.app:app --host 0.0.0.0 --port $PORT` | public domain |
| `mcp` | `python -m hr_agent.mcp_server --http` | private network only |

`web` discovers the 9 tools from `mcp` over Streamable HTTP on Railway's private
network. The committed index ships in the image — no build-time embedding, no
cold-start rebuild. Full setup and the six first-deploy gotchas: `deployed.md`.

---

## 7. Evaluation

### Method

`evaluation/eval_questions.jsonl` — **25 items across 5 categories**, each with
gold `doc_id`s, expected tools, and expected behavior:

| Category | n | Tests |
| --- | --- | --- |
| straightforward | 6 | single-doc policy Q&A |
| multi_doc | 5 | answers spanning 2–3 policies |
| tool | 6 | employee-data lookups + mixed policy/data |
| ambiguous | 4 | should ask one clarifying question |
| out_of_scope | 4 | should decline and redirect |

The harness (`run_eval.py`) drives the system **in-process** via `run_workflow`
(deterministic, CI-runnable with a stub; system latency is the tool-calling loop,
not HTTP framing). The **LLM judge** (`judges.py`) is a *different* model family
from the one under test (`openai/gpt-oss-20b` vs the `qwen` generator) to avoid
self-preference bias; it scores groundedness and answer-similarity in one call.
`--rejudge` re-scores saved answers without re-running generation.

### Results (`evaluation/results/eval-2026-09-01T13-04-11Z*`, 0 provider errors)

**Answer quality**

| Metric | Value | n |
| --- | --- | --- |
| Groundedness (LLM-judge, vs full gold docs) | **0.73** | 13 |
| Citation precision / recall / F1 | 0.55 / **0.86** / 0.64 | 13 |
| Partial match — ROUGE-L | 0.18 | — |
| Partial match — LLM-judge similarity | **0.72** | 16 |

**Agent behavior**

| Metric | Value | n |
| --- | --- | --- |
| Tool-selection accuracy (Jaccard) | 0.75 | 25 |
| Workflow-completion rate | 0.86 (6/7) | 7 |
| Escalation / clarification accuracy | 0.75 | 8 |
| False clarify/refuse rate | 0.00 | 17 |
| **Action-safety pass rate** | **1.00** | 25 |

**System**

| Metric | Value |
| --- | --- |
| Latency p50 / p95 / mean (s) | 3.6 / 32.8 / 8.4 |

### Ablation — retrieval `k`

RAG-only path, 16 answer items, `RETRIEVAL_K` swept:

| k | citation F1 | ROUGE-L | latency p50 (s) |
| --- | --- | --- | --- |
| 2 | **0.86** | 0.21 | 1.5 |
| 4 | 0.79 | 0.23 | 1.0 |
| 8 | 0.59 | 0.22 | 1.1 |

Citation F1 falls monotonically as `k` grows: recall is already saturated at
k=2 (the gold document is nearly always in the top 2), so every extra retrieved
section only adds citations the gold set does not credit, dragging precision
down. This mirrors the main run (default k=5: recall 0.86 ≫ precision 0.55) and
indicates a lower default `k` (≈3) would raise citation F1 at no measurable
recall cost on this corpus.

*(The tools-enabled vs RAG-only ablation on the 7 workflow items is pending a
free-tier token-budget reset; RAG-only cannot call the data tools, so PTO /
benefits / profile items cannot complete — the expected near-total collapse.)*

### Findings

1. **Out-of-scope routing is the weak point (0.50).** "What's the weather in
   Austin tomorrow?" retrieves the *weather / company-closure* policy section
   above the similarity threshold, so the deterministic scope gate passes it
   through. The agent then declines on its own, but that registers as `answer`,
   not a hard `refuse`. A keyword stop-list or an LLM intent check on borderline
   items would close the gap.
2. **Citation precision (0.55) lags recall (0.86)** — the agent over-cites
   sections pulled via `get_policy_section`. The `k` ablation shows the cheapest
   lever is a lower default `k`.
3. **Multi-doc synthesis is where grounding slips.** Single-doc answers score
   1.00 groundedness; `md-01` (fully-remote + relocate) drops to 0 by
   elaborating with request-workflow, insurance and tax details not in the cited
   sections.
4. **One tool miss:** `tl-03` ("who is my manager?") returned a PTO summary
   instead of the manager id (similarity 0.0) — the sole workflow-completion
   failure.
5. **Safety held: 25/25.** No destructive tool ran; the action item stopped at
   the confirmation gate.
6. **ROUGE-L (0.18) is not informative here** — 60–120-word prose vs one-line
   gold answers; the LLM-judge similarity score is the meaningful partial-match
   metric.

### Reproduce

```bash
python -m evaluation.run_eval                        # full 25-item judged run + RESULTS.md
python -m evaluation.run_eval --rejudge results/<f>.json   # re-score saved answers only
python -m evaluation.ablation --no-judge             # k sweep + tools-vs-RAG
python -m evaluation.run_eval --smoke --offline      # CI plumbing check, no tokens
```
