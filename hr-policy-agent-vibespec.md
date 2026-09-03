# HR Policy & Operations Agent

This is a vibespec. It describes an agentic AI assistant that helps employees of a hypothetical company (Northwind Robotics, Inc.) complete HR policy and operations tasks. The system combines Retrieval-Augmented Generation (RAG) over a corpus of internal policy documents with an agent orchestrator that plans, selects tools, calls one or more Model Context Protocol (MCP) servers, reads mock structured data (employee records, PTO balances, benefits elections), and produces grounded, cited responses with a concise operational trace. It is built for the Quantic "AI Engineering Techniques and Architectures" course project and is graded against that project's rubric.

## About
- version: 0.8.0
- author: Candace Wilson
- last updated: 2026-09-01

## Change History
- 2026-08-29: Initial version. Captures all planning decisions prior to any code generation.
- 2026-08-30 (Phase 1–2): Real RAG (deterministic multi-format chunker, Gemini
  embeddings, committed `sqlite-vec` index) and real MCP (`FastMCP` server as
  `src/hr_agent/mcp_server.py`, runtime tool discovery, LangGraph tool-calling
  loop). First deviations logged (see Issues).
- 2026-08-31 (Phase 3–5): Deterministic `classify_intent` gate; both demo
  workflows verified end-to-end; answer-focused UI + multi-turn sessions;
  two-service Railway deploy (live); GitHub Actions CI/CD gated on green.
- 2026-09-01 (Phase 6–7): 25-item evaluation harness with an independent LLM
  judge, `--rejudge`, and a retrieval-`k` ablation; `design-and-evaluation.md`,
  `ai-tooling.md`, README rewrite; merged to `main` (PR #1) and redeployed.
- 2026-09-01: Full reconciliation pass — corrected every drifted reference
  section (Specifications, Folder Structure, API/MCP signatures, Database,
  Implementation, Testing, Deployment) against the shipped code, completed the
  Issues log for all phases, checked off met Acceptance Criteria, fixed the
  Glossary's confirmation-gate contradiction.
- 2026-09-02/03 (Phase 9 — Tier 2): answer-aware citation selection (over-citation
  fix); `tl-03` tool-discipline changes (`_AGENT_SYSTEM` per-tool rules,
  `lookup_employee_profile` `manager_name`, nudge on filler-after-tool);
  `--rejudge` completion-flag bug fixed. **Full 25-item judged run 2026-09-03:**
  citation F1 0.64 → 0.86, groundedness 0.73 → 0.85, similarity 0.72 → 0.78,
  out-of-scope 0.50 → 1.00, gate accuracy 0.75 → 1.00, workflow completion 5/7
  (flat), action-safety 1.00. Tests 131 → 140. See Issues → Phase 9.
- 2026-09-01 (Phase 8 — Tier 1 hardening): off-topic keyword deny-list in the
  gate (4th `guardrail_scope` signal); `check_policy_compliance` made
  retrieval-backed; `create_mock_hr_ticket` / `draft_hr_email` /
  `list_policy_documents` returns fleshed out; dead `ingest/builder.py` deleted;
  CI actions bumped to v5. Tests 116 → 131. See Issues → Phase 8.

## Specifications
- type: full-stack web app with a React frontend and a Python FastAPI backend, plus a companion MCP service
- languages: Python 3.12 (backend + agent orchestration), JavaScript/React 18 (frontend — the plan called for React 19; shipped on 18.3)
- frameworks: React + Vite (frontend, plain JS — no TypeScript), FastAPI (web + API), LangGraph (agent orchestration), FastMCP / official Python MCP SDK (MCP server), langchain-mcp-adapters (MCP client wiring), sqlite-vec (vector store)
- target platform: Linux container on Railway (Hobby tier); also runs locally on macOS/Linux
- LLM provider: **multi-provider, one config switch** (`LLM_PROVIDER` = `gemini` | `groq` | `openai_compatible`). Production runs **Groq** `qwen/qwen3.8-27b`; the spec's original single-provider Gemini plan is deviation-logged in Issues.
- embedding provider: Google Gemini `gemini-embedding-001` (768-dim), kept on Gemini regardless of the generation provider — a separate free-tier quota
- evaluation judge provider: a model family **different** from the generation provider, to avoid self-preference bias — default Groq `openai/gpt-oss-20b`
- package managers: `pip` + `requirements.txt` for the Python backend (see Issues — `uv`/`uv.lock` was the original plan; `pip` was chosen instead), `npm` for the React frontend

### Dependencies
- python 3.12 (pinned via `.python-version`)
- fastapi, uvicorn[standard]
- google-genai (embeddings + Gemini generation)
- openai (Groq / OpenAI-compatible chat + the eval judge)
- langgraph, langchain-core, langchain-mcp-adapters, langchain-groq, langchain-google-genai, langchain-openai
- mcp (official Python MCP SDK)
- sqlite-vec
- pydantic v2, pydantic-settings
- markdown-it-py (markdown parsing for ingestion)
- beautifulsoup4 (HTML parsing for ingestion)
- pypdf (PDF parsing for ingestion)
- tiktoken (token counting for deterministic chunking)
- httpx (MCP Streamable HTTP client/server transport)
- python-dotenv (local env loading)
- pytest, pytest-asyncio (tests)
- ruff (lint + format config in `pyproject.toml`, line-length 100)
- rouge-score, numpy (evaluation: partial-match scoring, percentiles)

All versions are pinned in `requirements.txt` (the exact set the Docker image
installs); `pyproject.toml` declares the package and its dependency floor for
an editable install. No `uv.lock` — see Issues.

## Features
- Policy question answering grounded in an indexed corpus of company policy documents, with inline citations (document id, title, section) and supporting snippets.
- Multi-document retrieval for complex questions that span several policies.
- Guardrails that refuse or redirect out-of-corpus and non-HR questions, limit unsupported claims, and separate stated policy from recommendations.
- An agent orchestrator that interprets intent, decides whether RAG alone suffices, selects and calls MCP-exposed tools, handles failures, and synthesizes a final response.
- At least two multi-step HR workflows end-to-end, verified with recorded traces: remote-work eligibility and PTO request guidance (the deployed demo tasks). **Not fully met:** the plan named five (adding expense compliance, benefits triage, HR case triage); those three exist only as individual tool-requiring eval items (benefits lookup, PTO balance, employee profile, a confirmation-gated ticket), not as distinct named multi-step workflows with their own gold traces. Two-of-two on the hard requirement (Requirements/Acceptance Criteria); two-of-five on the "build and evaluate five" stretch goal.
- An MCP server exposing nine tools over Streamable HTTP; the agent discovers tools at runtime and calls them for real (no hard-coded direct function calls).
- Confirmation-gated mock actions: creating a mock HR ticket or drafting an HR email pauses for explicit user confirmation and never performs an irreversible action.
- A concise, logged operational trace of each request: intent, retrieved sources, tool calls with arguments, tool results, answer basis, and any escalation decision. No hidden chain-of-thought is exposed.
- A chat web UI with collapsible Citations and Tool Trace panels, confirm/deny controls, and one-click demo-task presets.
- A `/health` endpoint reporting app status, MCP connectivity, and vector-store status.
- An evaluation harness of 25 questions/tasks across five categories, reporting answer-quality, agent-behavior, and system metrics, plus at least one ablation.
- CI/CD via GitHub Actions: lint, tests (including MCP tool discovery and a tool call), and deploy only on green.

## Requirements

Functional:
- Ingest a corpus of policy documents in at least two source formats (this project uses **17 documents in four formats**: 13 Markdown, 2 PDF, 1 HTML, 1 plain text), clean them, and chunk them with a deterministic heading-aware strategy.
- Embed chunks with a free-tier embedding model and store them with metadata sufficient for citation (document id, title, section path, source snippet, source format, chunk index).
- Provide top-k retrieval (default k = 3; was 5 through Phase 7) with optional document filtering and optional LLM query rewriting.
- Inject retrieved chunks plus source metadata into the LLM prompt; generate answers that cite document ids/titles/sections and include supporting snippets.
- Include at least one question that requires retrieval from multiple documents (remote-work eligibility spans Remote & Hybrid Work, Out-of-State & International Remote Work, and Data Security policies).
- Provide an agent orchestrator (LangGraph custom graph) that classifies intent, routes to clarification / scope-refusal / agent execution, loops over tool calls, gates destructive actions, and composes a grounded final answer.
- Support at least two multi-step workflows end-to-end (met — see Features); the "build and evaluate five" stretch goal is not met.
- Emit a structured operational trace for every `/chat` request and return it in the response and render it in the UI.
- Handle failures gracefully: unavailable MCP tool/server (degrade to RAG-only with a caveat), unknown employee id (ask the user to confirm), insufficient policy evidence (state uncertainty, recommend HR, set escalation flag), ambiguous request (ask one clarifying question), tool-loop cap (stop and answer with what was gathered).
- Expose an MCP server with nine tools: `search_policy_documents`, `get_policy_section`, `list_policy_documents`, `check_policy_compliance`, `lookup_employee_profile`, `check_pto_balance`, `lookup_benefits_status`, `create_mock_hr_ticket`, `draft_hr_email`. At least one tool reads the policy corpus (`search_policy_documents`, `get_policy_section`, `list_policy_documents`, and — as of Phase 8 — `check_policy_compliance`); at least one uses mock structured data or performs a mock operation (five do).
- The agent must discover MCP tools at runtime and invoke them through the MCP layer.
- Provide a `/chat` endpoint returning final answer, citations, snippets, and a concise tool-call trace; a `/health` endpoint returning JSON status including MCP connectivity; and a way for a grader to reproduce the two demo tasks from the UI.
- Provide an evaluation set of 25 items covering straightforward policy Q&A, multi-document questions, tool-requiring tasks, ambiguous requests, and out-of-scope requests, each with gold answers / expected behavior. Report groundedness, citation accuracy, optional partial match, tool-selection accuracy, workflow-completion rate, escalation/clarification accuracy, action-safety pass rate, and latency p50/p95. Include at least one ablation — **shipped: a retrieval-k sweep** ({2, 4, 8}, real result: citation F1 falls 0.86→0.79→0.59 as k grows); tools-enabled vs RAG-only is built and run manually (`evaluation/ablation.py --only tools`) but not yet re-run after a free-tier token reset; chunk-size ablation is out of scope (only one ablation is required).

Non-functional:
- Reproducibility: pinned `requirements.txt` + Python version (`uv.lock` was the original plan — see Issues), deterministic chunking (byte-identical chunks for identical input), fixed `SEED` for any evaluation sampling. The built vector index is committed as a deterministic artifact and rebuilt+verified in CI.
- Cost: zero LLM/embedding cost via Gemini free tier; hosting on Railway Hobby (already owned). No paid database.
- Latency target: warm p50 under ~6 s and warm p95 under ~15 s for representative tasks on free-tier models; measured and reported, not guaranteed.
- Portability: the entire system runs locally as two plain `python` processes (web + MCP over Streamable HTTP), or as one process with MCP spawned over stdio for single-process local dev (see Issues — the original plan was `uv run`).

Security:
- All secrets (`GEMINI_API_KEY`, `GROQ_API_KEY`, any deploy tokens) are read from environment variables / Railway variables and never committed. `.env` is git-ignored; `.env.example` lists every variable.
- No real personal data. All employee, PTO, benefits, and ticket data is clearly synthetic.
- No irreversible or outward-facing actions: `create_mock_hr_ticket` and `draft_hr_email` are mock-only and confirmation-gated; `draft_hr_email` returns draft text and never sends.
- The MCP service is reachable only over Railway private networking in production.

### Out of Scope
- Real authentication, user accounts, or role-based access control (a single `employee_id` is supplied per session for demo purposes).
- Sending real email, filing real tickets, or integrating with any real HR/HRIS system.
- A production-grade or hosted vector database; multi-tenant support; horizontal scaling.
- Real PII, real company data, or any paid data source.
- Fine-tuning or training any model.
- Streaming token-by-token responses in the UI (responses are returned whole with the trace).

### Future Considerations
- ~~Swap the LLM provider via config only~~ **shipped** — `LLM_PROVIDER` switches between Gemini/Groq/OpenAI-compatible with no other code change; used mid-build to move off Gemini generation onto Groq.
- Add a second MCP server (e.g., a calendar/scheduling mock) without changing the client discovery flow.
- Optional reranking stage after retrieval.
- Persist sessions and traces to SQLite for longer-term analysis.
- Per-user auth and a real approval workflow for actions.

## Considerations
- This is a solo project on a fixed course timeline; scope is deliberately bounded and the corpus and mock datasets are small so the system runs on modest resources.
- The system must be reproducible and runnable by a grader both locally and at a shared deployed URL. Reproducibility of the two demo tasks from the UI is a hard requirement.
- Railway no longer offers a true free tier; this project uses Railway Hobby (paid, already owned). This is disclosed plainly in `deployed.md` and `ai-tooling.md`. Railway is explicitly named as an acceptable platform in the project brief.
- Railway Hobby services are always-on, so there is effectively no cold start. `deployed.md` documents this and describes what a sleeping free tier would do instead (~30–60 s first-request delay; no index rebuild needed because the index is committed).
- Free-tier LLMs are rate-limited and variable in quality; the agent caps tool-loop iterations, sets timeouts, and degrades gracefully.
- vibespec is used as the planning and scaffolding tool. It is not a graded deliverable. Code is generated phase by phase (see Setup / build phases), not in one pass, so the empirical parts (retrieval quality, prompt tuning, evaluation) can be iterated on real code.

## User Stories
- As an employee, I want to ask a plain policy question (e.g., "How much PTO do I accrue per month?") and get a short answer with a citation, so that I can trust it without reading the whole handbook.
- As an employee planning to work remotely from another state for six weeks, I want the assistant to check my profile, pull the relevant remote-work, tax/location, and data-security policies, assess compliance, and give me cited next steps, so that I know whether it is allowed and what approvals I need.
- As an employee, I want to ask whether I can take three days of PTO next week and have the assistant check my balance, confirm the approval rule, and offer to draft a note to my manager (only after I confirm), so that I can act on it immediately without accidental side effects.
- As an employee, I want to ask whether a specific expense (laptop, home-office chair, a trip) is reimbursable and get a compliant yes/no/conditional answer with citations, so that I do not submit a non-compliant claim.
- As an employee, I want to ask whether I am eligible for a benefit and have the assistant check my employment type and benefits status and either answer or tell me to escalate, so that I get an accurate answer.
- As an employee raising a sensitive workplace concern, I want the assistant to recognize it should be escalated, retrieve the grievance procedure, and offer to create a mock HR case summary (only after I confirm), so that I am routed correctly rather than given a canned answer.
- As an employee asking something out of scope (e.g., "What's the weather?"), I want a clear redirect, so that I understand the assistant's boundaries.
- As a grader, I want a `/health` endpoint and one-click demo presets, so that I can verify connectivity and reproduce the two demo tasks quickly.

### User Flow
Primary flow (`/chat` request):
1. User enters a message in the chat UI (a session `employee_id` is set, defaulting to a documented demo id).
2. `classify_intent` node determines the intent: `policy_qa`, `agentic_workflow`, `ambiguous`, or `out_of_scope`, and extracts an `employee_id` if mentioned.
3. Routing:
   - `out_of_scope` -> `guardrail_scope` returns a refusal/redirect; flow ends.
   - `ambiguous`, or a workflow that needs an `employee_id` that is not available -> `clarify` returns one clarifying question; flow ends.
   - otherwise -> `agent`.
4. `agent` node (bound to the discovered MCP tools) decides whether RAG alone is sufficient or tools are needed, and emits tool calls.
5. `tools` node executes each MCP tool call, appends a `tool_call` trace entry (`ok` or `error: <code>`), and captures citations from policy tools.
6. If a destructive tool (`create_mock_hr_ticket` or `draft_hr_email`) is pending, the graph stops with `pending_action` set (a two-call handshake, not a LangGraph interrupt — see Issues): the UI shows the proposed action with Confirm/Deny controls. The client re-POSTs `/chat` with the same `session_id` and `confirm: true` (executes) or `confirm: false` (drops it, adds a `confirmation` trace entry).
7. The `agent` <-> `tools` loop repeats until no tool calls remain or the iteration cap (`MAX_TOOL_ITERATIONS`, default 5; was 8 through Phase 7) is hit. A `nudge` node fires once if the model stalls with filler instead of an answer, pushing it back into the loop.
8. `compose` takes the last model message as the answer, attaches deduped citations, and appends a `compose` trace entry. If the model call itself failed, a fixed "could not reach the language model" message is used instead of fabricating an answer.
9. The web layer (`orchestration.arun_chat` / `web/app.py`) assembles the `/chat` response: `session_id`, `answer`, `citations`, `trace`, `escalation`, `intent`, optional `pending_action`, optional `llm_error`.
10. The UI renders the answer, the Citations panel, and the Tool Trace panel.

### Acceptance Criteria
- [x] A plain policy question returns an answer with at least one correct citation to the source document and section. *(verified: eval `straightforward` category, behavior accuracy 1.00.)*
- [x] The remote-work eligibility task retrieves from at least two distinct policy documents and calls `lookup_employee_profile` and `check_policy_compliance` before answering. *(verified trace, Phase 3: citations from 4 docs, both tools called in order — `build-note.md` §9d.)*
- [x] The PTO request task calls `check_pto_balance`, retrieves the PTO policy, and does not create a ticket or draft an email until the user confirms. *(verified trace, Phase 3, and `evaluation` item `tl-06` — `pending_action` set, no ticket created without `confirm: true`.)*
- [x] An out-of-scope question is refused/redirected without fabricating a policy answer. **Met (Tier 1).** `gate.py`'s `looks_off_topic()` deny-list (weather / sports / recipes / code / trivia / news) routes a non-personal match to `guardrail_scope` regardless of the retrieval score. The full 2026-09-03 judged run scores all 4 gold out-of-scope items `refuse` (**behavior accuracy 0.50 → 1.00**), 0 false positives on the other 21. See `design-and-evaluation.md` §7 finding 1.
- [x] An ambiguous question yields exactly one clarifying question rather than a guess. *(verified: eval `ambiguous` category, 4/4 correct; verified trace, Phase 3.)*
- [x] Every `/chat` response includes a non-empty `trace` array whose entries name the tools called, their argument summaries, and result summaries.
- [x] `/health` returns JSON with `status`, `mcp.connected`, `mcp.tools_discovered` (>= 5, actually 9), and a vector-store-loaded signal — implemented as `vector_store.index_present` (not `.loaded`; see API).
- [x] The agent obtains its tool list via MCP discovery at runtime; removing the MCP server causes `/health` to report `mcp.connected = false` and the agent to degrade to RAG-only with a caveat. *(the two-service split makes this a literal, documented demo — `deployed.md`.)*
- [x] CI fails if any test fails, and deployment does not run unless CI is green. *(Railway "Wait for CI" on both services; verified live on the Phase 1–7 merge to `main`.)*
- [x] `python scripts/build_index.py --verify` reports identical chunk count and content hash on two consecutive runs. *(`uv run` → plain `python`, see Issues; runs in CI on every push.)*
- [x] The evaluation harness produces `evaluation/RESULTS.md` with all required metrics and at least one ablation table.

## Architecture

The system is two deployable services built from one monorepo, plus a build-time ingestion pipeline.

```
                          +-------------------------------------------------+
                          |  Browser: React (JS) chat app                   |
                          |  message list | Citations panel | Trace panel   |
                          |  confirm / deny controls | demo presets         |
                          +-----------------------+-------------------------+
                                                  | HTTPS: GET / , POST /chat , GET /health
                                                  v
+---------------------------- Railway Service A: "web" -----------------------------------+
|  FastAPI (uvicorn)                                                                     |
|   - GET /            -> serves React app shell or static built assets                  |
|   - POST /chat       -> session store (in-memory) -> LangGraph orchestrator            |
|   - GET /health      -> app + MCP connectivity + vector-store status                   |
|                                                                                       |
|   LangGraph custom graph (build_agent_graph, gate=True, confirm_gate=True):            |
|     classify (deterministic, no LLM) -> [ clarify | guardrail_scope | agent ]          |
|     agent  <->  tools (ToolNode)      -- nudge -> agent on stalled output              |
|     agent  ->  confirm_gate (destructive call, two-call handshake) -> tools | declined |
|     agent  ->  compose  ->  END                                                        |
|                                                                                       |
|   MCP client (langchain-mcp-adapters): discovers tools, adapts them to LangGraph tools |
|   LLM client (llm.py): one config switch (gemini | groq | openai_compatible);          |
|     chat_model() for the loop, embed() always on Gemini, judge_complete() for eval     |
+----------------------------------------+----------------------------------------------+
                                         | MCP Streamable HTTP over Railway private network
                                         | MCP_SERVER_URL = http://<service-b>.railway.internal:$PORT/mcp
                                         v
+---------------------------- Railway Service B: "mcp" -----------------------------------+
|  FastMCP Streamable-HTTP server: 9 tools                                                |
|    RAG-backed:  search_policy_documents | get_policy_section |                          |
|                 list_policy_documents | check_policy_compliance                        |
|    Mock data:   lookup_employee_profile | check_pto_balance | lookup_benefits_status   |
|    Mock action (gated): create_mock_hr_ticket | draft_hr_email                         |
|                                                                                       |
|    - sqlite-vec index at data/index/index.sqlite   (loaded read-only)                  |
|    - mock_data/*.json                              (loaded read-only;                  |
|                                                     tickets appended to a temp copy)   |
|    - google-genai embeddings                       (query embedding for retrieval)     |
+---------------------------------------------------------------------------------------+

Build-time (local + CI):
   corpus/*.{md,pdf,html,txt}  ->  ingest pipeline (load -> clean -> chunk -> embed -> index)
                               ->  data/index/index.sqlite  (committed, deterministic; CI rebuilds and verifies)
```

Patterns:
- Facade: `mcp_client.discovery` exposes a single `get_tools()` / `get_tools_async()` / `health()` surface over the MCP transport.
- Dependency injection via config: LLM provider/model, embedding model, retrieval k, chunk size/overlap, seed, scope/escalation thresholds, and `MCP_SERVER_URL` are all injected from `config.py` (env-backed) so no provider or size choice is hard-coded.
- Separation of concerns: web/API, orchestration (graph + deterministic gate), MCP client, MCP server (tools inline in one module), retrieval/index, and mock data are distinct modules; the LLM provider is isolated behind `llm.py`.
- Human-in-the-loop, not a framework interrupt: the confirmation gate is a two-call `pending_action` handshake keyed off the emitted destructive tool call — `/chat` owns session state itself, so `interrupt_before` + a checkpointer was not needed (see Issues).
- Transport abstraction: MCP client selects Streamable HTTP when `MCP_SERVER_URL` is set, otherwise spawns the server over stdio for single-process local dev.

## Data

### Entities

#### PolicyDocument
- doc_id: string (stable slug, e.g. `remote-hybrid-work`)
- title: string
- source_path: string (path under `corpus/`)
- source_format: string (`md` | `pdf` | `html`)
- summary: string (one-line, used by `list_policy_documents` and scoping)

#### PolicyChunk
- chunk_id: string (`<doc_id>#<chunk_index>`)
- doc_id: string (references PolicyDocument; the corpus filename stem, e.g. `02-pto-and-vacation-policy`)
- doc_title: string
- section_path: string (e.g. `Pto And Vacation Policy > Eligibility`)
- chunk_index: integer
- source_format: string
- text: string
- embedding: float32[768] (Gemini `gemini-embedding-001`, L2-normalized so cosine similarity == dot product; no char-offset field is stored — the committed index's `chunks` table is `chunk_id, doc_id, doc_title, section_path, chunk_index, source_format, text`, see Database)

#### Employee
- employee_id: string (e.g. `E-1007`)
- name: string
- title: string
- department: string
- employment_type: string (`full_time` | `part_time` | `contractor` | `intern`)
- hire_date: string (yyyy-mm-dd)
- work_state: string (US state code or `IE`)
- office_location: string (references OfficeLocation.location_id)
- manager_id: string (references Employee.employee_id, nullable)
- exempt_status: string (`exempt` | `non_exempt`)

#### PtoBalance
- employee_id: string (references Employee)
- accrual_rate_hours_per_month: number
- accrued_hours: number
- used_hours: number
- pending_hours: number
- carryover_hours: number

#### BenefitsElection
- employee_id: string (references Employee)
- medical_plan: string (`none` | `hdhp` | `ppo`)
- dental: boolean
- vision: boolean
- retirement_401k_pct: number
- fsa_annual: number
- eligibility_status: string (`eligible` | `pending` | `ineligible`)
- effective_date: string (yyyy-mm-dd)

#### OfficeLocation
- location_id: string (e.g. `austin-hq`, `remote-ca`, `dublin`)
- city: string
- state: string
- country: string
- timezone: string
- legal_entity: string
- remote_tax_notes: string

#### HrTicket
- ticket_id: string (`TKT-<n>`, generated)
- employee_id: string (references Employee)
- category: string (`pto` | `remote_work` | `expense` | `benefits` | `workplace_concern` | `other`)
- summary: string
- details: string
- status: string (always `created_mock`)
- created_at: string (ISO 8601)

  **Reconciled (Tier 1).** The live `create_mock_hr_ticket(employee_id, issue)`
  MCP tool now returns this shape: a deterministic `ticket_id` of `HR-<sha1[:6]>`
  over `(employee_id, issue)`, plus `category`, `summary`, `details`,
  `status: "created_mock"`, `created_at`, and a `note`. It still never touches
  `mock_data/hr_tickets.json` (no ticket is created without confirmation, and
  nothing is persisted) — see API.

### Relationships
- PolicyDocument has a one-to-many relationship with PolicyChunk.
- Employee has a one-to-one relationship with PtoBalance and with BenefitsElection.
- Employee has a many-to-one self relationship via `manager_id`.
- Employee has a many-to-one relationship with OfficeLocation.
- Employee has a one-to-many relationship with HrTicket (mock, session-scoped).

## Folder Structure

**Deviation** from the original plan throughout: no top-level `mcp/` package
(shadows the `mcp` PyPI SDK — see Issues), no `rag/` subpackage (retrieval,
answering, and guardrails live as top-level modules), no TypeScript frontend,
no `uv.lock` (`requirements.txt` instead), no shell-script runners (plain
commands in `README.md` / `deployed.md`). The tree below is the shipped one.

```
hr-policy-agent/
├── README.md
├── design-and-evaluation.md
├── ai-tooling.md
├── deployed.md
├── architecture-notes.md          # early one-page sketch, superseded by design-and-evaluation.md
├── corpus-facts.md                # every concrete figure in corpus/, kept consistent with mock_data/
├── CLAUDE.md                      # coding conventions
├── AGENTS.md                      # generic-agent mirror of CLAUDE.md
├── hr-policy-agent-vibespec.md
├── vibespec-instructions.md
├── structure.md
├── pyproject.toml                 # package + [tool.ruff]; no uv.lock
├── requirements.txt                # pinned deps -- the set the Docker image installs
├── .python-version
├── .env.example
├── .gitignore                     # build-note.md (private dev log) is git-ignored
├── Dockerfile                     # one shared image; per-service start command differs
├── docker-compose.yml             # local two-service mirror
├── .dockerignore
├── .github/
│   └── workflows/
│       └── ci.yml
├── corpus/                        # 17 docs, 4 formats
│   ├── 01-handbook-overview-and-code-of-conduct.md
│   ├── 02-pto-and-vacation-policy.md
│   ├── 03-holidays-and-company-closure.md
│   ├── 04-remote-and-hybrid-work-policy.md
│   ├── 05-out-of-state-and-international-remote-work.md
│   ├── 06-data-security-and-acceptable-use.pdf
│   ├── 07-expense-and-reimbursement-policy.md
│   ├── 08-travel-policy.md
│   ├── 09-benefits-guide.pdf
│   ├── 10-leave-of-absence-policy.md
│   ├── 11-onboarding-and-equipment-provisioning.md
│   ├── 12-workplace-conduct-and-grievance-procedure.html
│   ├── 13-compensation-and-payroll.md
│   ├── 14-performance-and-development.md
│   ├── 15-parental-and-family-leave.md
│   ├── 16-workplace-health-and-safety.md
│   └── 17-information-classification-standard.txt
├── mock_data/
│   ├── employees.json
│   ├── pto_balances.json
│   ├── benefits_elections.json
│   ├── office_locations.json
│   └── hr_tickets.json
├── data/
│   └── index/
│       ├── index.sqlite
│       └── manifest.json          # chunk count, content hash, build config, embedding model
├── frontend/                      # plain JS + React (no TypeScript)
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── App.jsx                # single-file SPA: chat, citations, trace, confirm/deny
│       └── styles.css
├── src/
│   └── hr_agent/
│       ├── __init__.py
│       ├── config.py               # every env-backed setting
│       ├── llm.py                  # ONLY file importing a model SDK; multi-provider
│       ├── retrieval.py            # vector-first search + keyword TF-IDF fallback
│       ├── vector_store.py         # sqlite-vec read/write
│       ├── answering.py            # RAG-only synthesis (fallback path) + citations
│       ├── guardrails.py           # scope/escalation thresholds on retrieval score
│       ├── routing.py              # mock-action phrase detection (ticket/email)
│       ├── directory.py            # employee id/name resolution against mock_data
│       ├── orchestration.py        # run_workflow / arun_chat: agent loop or RAG-only degrade
│       ├── mcp_server.py           # FastMCP server, all 9 tools inline
│       ├── ingest/
│       │   ├── chunker.py          # deterministic heading-aware multi-format chunking
│       │   └── indexer.py          # build/verify the sqlite-vec index + manifest
│       ├── agent/
│       │   ├── graph.py            # the LangGraph StateGraph (classify/agent/tools/confirm_gate/compose/nudge)
│       │   ├── gate.py             # deterministic classify_intent (no LLM)
│       │   └── state.py            # AgentState TypedDict
│       ├── mcp_client/
│       │   └── discovery.py        # MultiServerMCPClient facade: get_tools() / health()
│       └── web/
│           ├── app.py              # FastAPI: /, /chat, /health, lifespan MCP discovery
│           └── sessions.py         # in-memory SessionStore
├── evaluation/
│   ├── __init__.py
│   ├── eval_questions.jsonl        # 25-item gold set
│   ├── schema.py                   # EvalItem pydantic model + loader
│   ├── metrics.py                  # pure: P/R/F1, Jaccard, ROUGE-L, percentiles
│   ├── judges.py                   # independent LLM judge: groundedness + similarity
│   ├── run_eval.py                 # runner + --rejudge; writes results/*.json + RESULTS.md
│   ├── ablation.py                 # retrieval-k sweep, tools-vs-RAG
│   ├── RESULTS.md
│   └── results/
│       ├── .gitkeep
│       └── eval-*.json, ablation-*.json   # committed run artifacts
├── tests/                          # 18 files, 140 tests
│   ├── conftest.py
│   ├── _fakes.py                   # ScriptedChatModel test double
│   ├── test_app.py
│   ├── test_ingestion.py
│   ├── test_chunker.py
│   ├── test_retrieval.py
│   ├── test_guardrails.py
│   ├── test_routing.py
│   ├── test_directory.py
│   ├── test_gate.py
│   ├── test_agent_loop.py
│   ├── test_orchestration.py
│   ├── test_workflows.py
│   ├── test_mcp.py
│   ├── test_sessions.py
│   ├── test_answering.py
│   ├── test_llm.py
│   ├── test_embeddings.py
│   └── test_evaluation.py
└── scripts/
    ├── build_index.py              # chunk -> embed -> index; --verify
    └── build_corpus_formats.py     # regenerates the PDF/HTML corpus files from Markdown
```

## Setup

**Deviation:** the plan called for `uv`; the shipped project uses a plain venv
+ `pip install -e .` + pinned `requirements.txt` (see Issues) — no `uv run`
prefix on any command below.

- Create a Python 3.12 venv and install: `python3.12 -m venv .venv && . .venv/bin/activate && pip install -e .`
- Install the frontend dependencies: from `frontend/`, run `npm install`.
- Copy `.env.example` to `.env` and set `GEMINI_API_KEY` (embeddings) and
  `GROQ_API_KEY` (generation; or switch `LLM_PROVIDER`). Leave `MCP_SERVER_URL`
  unset for single-process local dev (the web app spawns the MCP server over
  stdio), or set it to `http://127.0.0.1:8765/mcp` to run the MCP server as a
  separate local process.
- Build the vector index: `python scripts/build_index.py`. The committed
  `data/index/index.sqlite` is already valid; rebuild only after changing the
  corpus or chunking config.
- Run the MCP server (separate-process mode): `python -m hr_agent.mcp_server --http --port 8765`.
- Run the backend: `python -m uvicorn hr_agent.web.app:app --port 8000`.
- Run the React frontend: `cd frontend && npm run dev` (Vite default port 5173). Open http://127.0.0.1:5173.
- For a single-host local demo, the frontend can proxy API calls to the FastAPI backend at `http://127.0.0.1:8000`.

Environment variables (see `.env.example` — this is a representative subset, not exhaustive):
- `LLM_PROVIDER` (`gemini` | `groq` | `openai_compatible`, default `gemini`) / `LLM_MODEL` (default `gemini-3.6-flash`) / `LLM_BASE_URL` / `LLM_MAX_OUTPUT_TOKENS`
- `GEMINI_API_KEY`, `GROQ_API_KEY`, `LLM_API_KEY` (per-provider keys)
- `EMBEDDING_MODEL` (default `gemini-embedding-001`) / `EMBEDDING_DIM` (default `768`)
- `MCP_SERVER_URL` (optional; when set, web app uses Streamable HTTP instead of stdio) / `MCP_TRANSPORT` / `MCP_HOST` / `MCP_PORT` (default `8765`)
- `RETRIEVAL_K` (default `3`) / `SCOPE_THRESHOLD` (default `0.55`) / `ESCALATION_THRESHOLD` (default `0.60`)
- `CHUNK_SIZE` (default `800` tokens) / `CHUNK_OVERLAP` (default `120` tokens)
- `SEED` (default `42`) / `MAX_TOOL_ITERATIONS` (default `5`)
- `EVAL_JUDGE_PROVIDER` (default `groq`) / `EVAL_JUDGE_MODEL` (default `openai/gpt-oss-20b`) / `EVAL_JUDGE_PACE_SECONDS`
- `STATIC_DIR` (production: where the built SPA is copied in the image)

### Validation
- `ruff check .` completes with no errors.
- `pytest -q` passes (140 tests).
- `python scripts/build_index.py --verify` reports identical chunk count and content hash across two runs.
- `curl localhost:8000/health` returns JSON with `status: "ok"`, `mcp.connected: true`, `mcp.tools_discovered: 9`, `vector_store.index_present: true`.
- In the UI, the two demo presets (remote-work eligibility, PTO request) each complete end-to-end, showing tool calls in the Trace panel and at least one citation.

## UI

A React (plain JavaScript, not TypeScript — see Issues) single-page chat
interface that talks to the Python FastAPI backend. The frontend is a Vite app
under `frontend/` and renders all conversational, citation, and trace views
from API responses. Answers render as markdown (`marked` + `dompurify`);
citations collapse to a "Sources (n)" superscript-linked list.

- A header with the app name, the active `employee_id` selector (a small dropdown of documented demo ids), and a quick link to `/health`.
- A scrolling conversation area: user messages right-aligned; assistant messages left-aligned as cards.
- Each assistant card has the answer text (with inline `[doc_id]` markers), followed by two collapsible sections:
  - Citations: a list of `title -> section` with the supporting snippet.
  - Tool Trace: an ordered list of steps (intent, retrieval, each tool call with its argument summary and result summary, confirmation, escalation, answer basis).
- When the response contains a `pending_action`, the card shows a highlighted block describing the proposed mock action (tool name + argument summary) with Confirm and Deny buttons. Confirm re-submits with a `confirm` flag; Deny cancels and the assistant continues without the action.
- Below the message composer: two preset buttons that populate and send the two demo-task prompts.
- An escalation badge appears on the card when `escalation` is true.

### Layout
Single column, max width ~840 px, centered. Vertical flow: header, conversation area (flex-grow, scrolls), message composer, preset button row. Light and dark friendly via CSS variables. The frontend is designed as a reusable component tree rather than a handwritten DOM layout.

### Pages
- `/` : the main chat page rendered by the React app.
- Optional `/health` : served by FastAPI for diagnostics, not a React view.

## API

All responses are JSON except `GET /`.

### Endpoints

**Deviation:** field names below match the shipped API, not the original plan
— `/health.vector_store` gained `index_present`/`embedding_model`/
`embedding_key_configured` instead of a single `loaded` boolean and a `version`
field, and picked up a `retrieval.active_method` block; `/chat` gained `intent`
and `llm_error`. Every MCP tool signature is simpler than originally planned —
see the table below and Issues.

- **GET /** : Serves the built SPA (production) or is skipped so Vite serves it in dev.
- **POST /chat** : Body `{ "message": string, "employee_id"?: string, "session_id"?: string, "confirm"?: boolean }`. Returns:
  ```
  {
    "session_id": string,
    "answer": string,
    "citations": [ { "doc_id": string, "title": string, "section": string, "snippet": string } ],
    "trace": [ { "step": int, "type": string, "name"?: string, "args_summary"?: string,
                 "result_summary"?: string } ],
    "escalation": boolean,
    "pending_action": { "tool": string, "employee_id": string, "description": string } | null,
    "intent": string,          // "policy_qa" | "agentic_workflow" | "clarify" | "out_of_scope" | ...
    "llm_error": string | null // set only when the model call itself failed
  }
  ```
  When `pending_action` is present, the client re-calls `POST /chat` with the same `session_id` and `confirm: true` (or `confirm: false` to cancel).
- **GET /health** : Returns:
  ```
  {
    "status": "ok",
    "mcp": { "connected": boolean, "tools_discovered": int, "transport": "streamable_http" | "stdio" },
    "vector_store": { "index_present": boolean, "chunks": int,
                       "embedding_model": string, "embedding_key_configured": boolean },
    "retrieval": { "active_method": "vector" | "keyword" }
  }
  ```
  `mcp` is live-probed on a 15s TTL, so stopping the MCP service flips
  `connected` within ~15s (the degradation demo).

### MCP tool interface (Service B, not HTTP REST)
Discovered via MCP `list_tools`. Each tool has a Pydantic input schema and returns a typed JSON object (errors are returned as `{ "error": "<code>", "message": "<text>" }`, never raised across the wire).

- `search_policy_documents(query: str, k: int = 3)` -> `{ "results": [ { "doc_id", "title", "section", "snippet", "source_format", "score" } ] }` — **keyword TF-IDF**, not the vector index (the gate/RAG-only path uses vector separately; see Architecture)
- `get_policy_section(doc_id: str, section: str | None = None)` -> `{ "doc_id", "section", "content" }` (all sections joined if `section` omitted) or `{ "error": "not_found" }`
- `list_policy_documents()` -> `{ "documents": [ { "doc_id", "title" }, ... ] }` (title = doc-id stem, de-hyphenated + title-cased)
- `check_policy_compliance(question: str)` -> `{ "question", "status": "ok" | "requires_review" | "not_applicable", "message": string, "relevant_sections": [ { "doc_id", "section", "snippet" } ] }` — **retrieval-backed**: runs `retrieve()` for the top 3 policy sections and returns them as evidence; `status` is a keyword-derived hint (relocation / out-of-state / international remote / expense / leave / termination / grievance → `requires_review`; PTO / vacation / holiday → `ok`; empty retrieval → `not_applicable`). Advisory, not an LLM call and not authoritative — the cited sections are the substance.
- `lookup_employee_profile(employee_id: str)` -> Employee object **plus a resolved `manager_name`** (from `manager_id`, or `null` at the top of the chain), or `{ "error": "not_found", "message" }`
- `check_pto_balance(employee_id: str)` -> PtoBalance object + derived `available_hours` (accrued − used − pending) or `{ "error": "not_found", "message" }`
- `lookup_benefits_status(employee_id: str)` -> BenefitsElection object or `{ "error": "not_found", "message" }`
- `create_mock_hr_ticket(employee_id: str, issue: str)` -> `{ "ticket_id": "HR-<sha1[:6]>", "employee_id", "category", "summary", "details", "status": "created_mock", "created_at", "note" }` — deterministic id over `(employee_id, issue)`; shape matches the `mock_data/hr_tickets.json` sample rows; confirmation-gated by the orchestrator; never persisted
- `draft_hr_email(employee_id: str, topic: str)` -> `{ "employee_id", "topic", "draft" }` — `draft` is one subject+body string templated on the topic and the employee's resolved first name; confirmation-gated; never sends

## Database
No relational database. Storage is:
- `data/index/index.sqlite` : a SQLite file with the `sqlite-vec` extension. One virtual table `vec_chunks(embedding float[EMBEDDING_DIM])` plus a companion table `chunks(rowid INTEGER PRIMARY KEY, chunk_id TEXT UNIQUE, doc_id, doc_title, section_path, chunk_index, source_format, text)` — no char-offset columns. Loaded read-only by both services. Committed to the repo as a deterministic build artifact; `data/index/manifest.json` records chunk count, SHA-256 of concatenated chunk texts, chunk size/overlap, embedding model, and build timestamp.
- `mock_data/*.json` : synthetic structured data, loaded read-only. `create_mock_hr_ticket` returns an in-memory response only — it never writes to any file, committed or temporary (simpler than originally planned, same guarantee: `hr_tickets.json` is never mutated).
- Sessions and traces: in-memory `SessionStore` in the web service (`web/sessions.py`), keyed by `session_id`: message history + a learned `employee_id`. Not persisted (see Future Considerations).

## Implementation

**This whole section is rewritten against the shipped code.** The original
plan's `rag/`, `mcp/tools/`, and per-loader-format modules were never built
that way; see Folder Structure for why.

### Services
- **web (`src/hr_agent/web/app.py`)**: FastAPI app. Startup (`lifespan`): discover MCP tools (degrade to RAG-only on failure), create the `SessionStore`. Routes: `/` (serves the built SPA if present, else nothing — Vite serves it in dev), `/chat`, `/health`. No explicit shutdown step — `langchain-mcp-adapters` opens a fresh session per call.
- **mcp (`src/hr_agent/mcp_server.py`)**: FastMCP server exposing the nine tools, defined inline in `build_mcp_server()`. Loads the corpus/index and `mock_data/*.json` lazily per call (no separate startup step). Transport: `python -m hr_agent.mcp_server` for stdio (spawned by the web app), `--http` for Streamable HTTP (standalone/production).

### Modules
- `config.py`: a Pydantic Settings object (`pydantic-settings`, env file `.env`) with every setting used anywhere in the app — see Setup for the full env var list. No separate `seeds.py`; `SEED` is read directly from `settings.seed` where needed (chunking itself needs no seed — it is deterministic by construction).
- `llm.py`: the **only** file importing a model SDK. `chat_model()` returns a LangChain `BaseChatModel` for the tool-calling loop (`ChatGoogleGenerativeAI` / `ChatGroq` / `ChatOpenAI`, selected by `LLM_PROVIDER`); `generate_answer()` is the plain-string path for RAG-only synthesis; `embed()` is always Gemini regardless of `LLM_PROVIDER` (a separate quota); `judge_complete()` / `judge_available()` back the evaluation judge on its own provider/model.

### Ingestion (`src/hr_agent/ingest/`)
- `chunker.py`: `load_corpus_documents` + `load_sections` handle all four corpus formats (Markdown via `markdown-it-py`, HTML via `beautifulsoup4`, PDF via `pypdf`, plain text) in one module rather than per-format loader files. `chunk_corpus(corpus_dir, chunk_size, chunk_overlap)` walks each document's sections and packs whole sentences into token windows (tokens approximated as `len(text)/4`, a deterministic offline proxy), never splitting a sentence, carrying a `section_path` breadcrumb. Output: ordered `PolicyChunk` records (`chunk_id`, `doc_id`, `doc_title`, `section_path`, `chunk_index`, `source_format`, `text`). Identical input + config yields byte-identical chunks (`chunks_content_hash`).
- `indexer.py`: `build_index(chunks, vectors, index_path)` creates `index.sqlite` (the `chunks` table + `vec_chunks` virtual table) and `manifest.json`; `verify_index()` re-chunks and compares the content hash to the committed manifest (the `--verify` path, run in CI). `tests/test_ingestion.py` exercises this end to end (`chunk_corpus` → `build_index` → read the sqlite rows back).
- Embedding is not a separate module: `scripts/build_index.py` calls `llm.embed()` directly between chunking and indexing.

### Retrieval, answering, guardrails (top-level modules, not a `rag/` subpackage)
- `retrieval.py`: `retrieve_passages(query, k, corpus_dir)` — vector-first via `vector_store.search()` (embeds the query with Gemini, sqlite-vec KNN), falling back to an in-module keyword TF-IDF retriever (`retrieve()`) when there is no index, no embedding key, or the embed call fails. Returns `(results, meta)` with `meta.method` so callers can log which path ran.
- `vector_store.py`: read/write the `sqlite-vec` index; `search()` returns the same shape as the keyword retriever so callers don't care which one ran.
- `answering.py`: the RAG-only path — `generate_final_answer(query, tool_result, corpus_dir, k)` retrieves, builds the answer prompt (answer only from context, cite `[doc_id]`, say so plainly if the tools/context don't answer the question), calls `llm.generate_answer()` or falls back to template synthesis without a key, and returns `{answer, citations, trace, escalation}`.
- `guardrails.py`: `is_in_scope(results)` / `needs_escalation(results)` / `top_score(results)` — pure functions over a retrieval-result list and the `SCOPE_THRESHOLD` / `ESCALATION_THRESHOLD` config values. `SCOPE_REFUSAL` is the fixed redirect text.
- `routing.py` / `directory.py`: `TICKET_PHRASES` / `EMAIL_PHRASES` (mock-action detection) and `resolve_employee()` / `get_employee_name()` (id/name resolution against `mock_data/employees.json`) — the deterministic signals `agent/gate.py` is built from.

### Agent (`src/hr_agent/agent/`)
- `state.py`: `AgentState` (`TypedDict`, not the originally planned field set) — `query`, `corpus_dir`, `employee_id`, `history`, `messages` (LangGraph `add_messages`-annotated), `tool_trace`, `citations`, `iterations`, `nudges`, `answer`, `llm_error`, `escalation`, `intent`, `gate_route`, `gate_message`, `scope_score`, `confirm`, `pending_action`.
- `gate.py`: `decide(query, employee_id_hint, retrieval_results, retrieval_method, has_history)` — **deterministic, no LLM.** Routes `clarify` (unknown/missing employee id, or a narrow first-person-yes/no ambiguity regex), `scope` (an off-topic keyword deny-list — `looks_off_topic()`, weather / sports / recipes / code / trivia / news on a non-personal query, method-independent — **or** a vector-only retrieval score below `SCOPE_THRESHOLD` skipped on a follow-up), or `agent`.
- `graph.py`: `build_agent_graph(tools, model, confirm_gate, gate)` — no separate `nodes.py`/`trace.py` modules; every node is a closure inside this one function. Nodes: `classify` (calls `gate.decide`), `clarify`, `guardrail_scope`, `agent` (LLM bound to the MCP tools), `tools` (`ToolNode`, appends trace entries, collects citations), `confirm_gate` / `declined` (the two-call handshake — see Issues, not `interrupt_before`), `nudge` (recovers a model that stalls with filler once, including filler that follows a tool call), `compose` (takes the last AI message as the answer; keeps only citations whose document the answer names via `_select_citations`, capped fallback to retrieval order). `arun_workflow()` / `run_workflow()` are the entry points; `orchestration.py` wraps them with the RAG-only degradation.

### MCP client (`src/hr_agent/mcp_client/`)
- `discovery.py`: builds a `MultiServerMCPClient` (langchain-mcp-adapters). If `MCP_SERVER_URL` is set -> Streamable HTTP; else -> stdio spawning `python -m hr_agent.mcp_server` (not `python -m mcp.server` — see Issues). Exposes `get_tools()` / `get_tools_async()` (LangGraph-compatible) and `health()` (connected?, tool count, transport).

### MCP tools (`src/hr_agent/mcp_server.py`, not a `mcp/tools/` package)
All nine tools are `@server.tool()`-decorated closures inside `build_mcp_server()`,
using inline dict returns rather than separate Pydantic schema/policy/compliance/
employees/pto/benefits/actions modules. Exact signatures and return shapes: API
section. `check_policy_compliance` retrieves the top 3 policy sections as
evidence and derives `status` from a keyword hint — no LLM call.
`create_mock_hr_ticket` (deterministic `HR-<hash>` id) / `draft_hr_email`
(templated on topic + employee) never persist anything.

### Web (`src/hr_agent/web/`)
- `app.py`: FastAPI routes and lifespan wiring described under Services.
- `sessions.py`: `SessionStore` — in-memory `{session_id: Session}`, `Session` holds `history` (list of prior turns) and a learned `employee_id`; `get()` generates a `session_id` if absent; `record_turn()` is only called once a turn is not a pending confirmation.
- No `static/` folder in the repo — the built SPA (`frontend/dist` in dev, `STATIC_DIR` in the container) is mounted at request time if present.

### Scripts (`scripts/`)
- `build_index.py`: chunk → embed → `indexer.build_index`; `--verify` re-chunks and compares to the manifest (offline, no embedding call).
- `build_corpus_formats.py`: regenerates the PDF/HTML corpus documents from their Markdown sources (keeps the four-format corpus reproducible from one source of truth per document).
- No `run_local.sh` / `run_mcp_local.sh` — the equivalent plain commands are in Setup, `README.md`, and `deployed.md`.

## Testing

**140 tests across 18 files** (offline by default — an autouse `conftest.py`
fixture forces the no-LLM path; tests that need tool-calling inject a
`ScriptedChatModel` from `tests/_fakes.py`). File names differ throughout from
the original plan; grouped by what they actually cover:

### Unit tests
- `test_chunker.py`: chunking determinism (identical chunk count + content hash
  across two runs), heading-aware `section_path` breadcrumbs, never splitting a
  sentence, multi-format loading (md/html/pdf/txt). `test_ingestion.py`: the
  full `chunk_corpus` → `indexer.build_index` → sqlite read-back path, plus the
  chunk/vector length-mismatch guard.
- `test_retrieval.py`, `test_guardrails.py`: retrieval relevance (a PTO query's
  top chunk is `doc_id="02-pto-and-vacation-policy"`), `is_in_scope` /
  `needs_escalation` threshold behavior, keyword-vs-vector fallback.
- `test_routing.py`, `test_directory.py`, `test_gate.py`: mock-action phrase
  detection, employee id/name resolution, and the full deterministic
  `classify_intent` decision table (clarify / scope / agent) — including the
  off-topic deny-list (fires regardless of retrieval method, exempts personal
  workflows) and the gold-set audit that caught first-person phrasing
  false-positives (see `ai-tooling.md`).
- `test_answering.py`, `test_llm.py`, `test_embeddings.py`: RAG-only synthesis
  + template fallback, provider selection (`LLM_PROVIDER` switch), embeddings
  (live, skipped without a key).
- `test_sessions.py`: `SessionStore` history + learned `employee_id`.

### Integration tests
- `test_agent_loop.py`, `test_orchestration.py`, `test_workflows.py`: the full
  LangGraph loop with a `ScriptedChatModel` over the real MCP tools —
  confirmation gate (`pending_action`, no ticket without `confirm: true`,
  exactly one on confirm, a `confirmation` trace entry on decline), trace shape
  (only the allowed operational fields), unknown-employee redirect instead of a
  fabricated profile, and the two graded demo workflows end-to-end (remote-work
  eligibility, PTO request — verified traces in `build-note.md` §9d).
- `test_mcp.py`: tool discovery (stdio, exactly nine tools, non-empty input
  schemas), a real tool call (`list_policy_documents`, `check_pto_balance`
  returning a numeric `available_hours`), degradation (MCP client pointed at an
  unreachable URL → `discovery.health().connected == False` and the graph still
  returns a RAG-only answer with a caveat).
- `test_app.py`: FastAPI `TestClient` + lifespan boots; `GET /health` returns
  200 with the documented shape and `mcp.tools_discovered >= 5`; `POST /chat`
  smoke — a plain policy question returns 200 with a non-empty `answer`, ≥1
  citation, and a non-empty `trace`.
- `test_evaluation.py`: the evaluation harness itself — gold-set validity
  (every `doc_id` is a real corpus stem, categories/behaviors are consistent),
  every pure metric function, judge-response parsing (tolerates prose around
  the JSON, clamps out-of-range scores), and an offline end-to-end smoke run
  with a stub model.

### End-to-End
- Covered by the evaluation harness (`evaluation/run_eval.py`), run **in-process**
  via `run_workflow` (a deliberate deviation from "against a locally running pair
  of services" — see Issues): the 25-item set exercises all five categories, and
  the two demo tasks are covered by `test_workflows.py`. CI runs a 6-item offline
  smoke subset (`--smoke --offline`, zero tokens); the full judged run is
  executed locally and its `RESULTS.md` + `results/*.json` are committed.

Evaluation metrics (reported in `evaluation/RESULTS.md`):
- Answer quality: groundedness (LLM-judge, 0-1, against the full text of the
  gold policy documents — not just post-run citation snippets, see Issues),
  citation accuracy (precision/recall/F1 of returned `doc_id`s vs gold), partial
  match (ROUGE-L + LLM-judge similarity vs short gold answers).
- Agent behavior: tool-selection accuracy (Jaccard of actual vs expected tools), workflow-completion rate, escalation/clarification accuracy, action-safety pass rate.
- System: latency p50/p95 over the 25 items, in-process (excludes HTTP framing — negligible against the tool-calling loop's 3-30s range).
- Ablation: **shipped** — retrieval k in {2, 4, 8} (citation F1 falls 0.86 → 0.79 → 0.59 as k grows). Tools-enabled vs RAG-only on the 7 workflow items is built (`evaluation/ablation.py`) and has been run manually but not yet committed after a clean free-tier token budget. Chunk-size ablation is out of scope (rubric requires only one ablation).

## Deployment

**Live:** https://web-production-1fa45.up.railway.app. Deviates from the
original plan in build tooling (`Dockerfile`, not Nixpacks/`uv` detection —
there is no `uv.lock` to detect) and the deploy mechanism (Railway's own
"Wait for CI" gate, not a `deploy` job in the workflow — see Issues). Full
detail and the six first-deploy gotchas: `deployed.md`.

- Deployment environment: Railway (Hobby tier — paid, already owned; disclosed
  in `ai-tooling.md` and `deployed.md`), two services from one GitHub repo,
  built from **one shared `Dockerfile`**, differing only in start command.
  - Service `web`: start command *(Dockerfile default)*
    `uvicorn hr_agent.web.app:app --host 0.0.0.0 --port $PORT`. Public HTTPS
    domain. Variables: `PORT=8000`, `MCP_SERVER_URL=http://mcp.railway.internal:8765/mcp`,
    `LLM_PROVIDER`, `LLM_MODEL`, `GROQ_API_KEY`, `GEMINI_API_KEY`.
  - Service `mcp`: start command `python -m hr_agent.mcp_server --http`
    (no `--port` — Railway's Custom Start Command is not shell-expanded, so the
    server reads `$PORT` from the environment itself). Private networking only.
    Variables: `PORT=8765` only — the MCP tools are retrieval + mock-data
    lookups, no LLM key needed.
- Both services build the same Docker image; `pip install -e .` (editable —
  a non-editable install breaks the `Path(__file__).parents[2]` data-path
  lookups, see Issues). The committed `data/index/index.sqlite` and
  `mock_data/` ship in the image, so no build-time embedding calls are needed.
- Railway is configured to deploy only after the GitHub Actions CI checks pass
  (per-service **Wait for CI** toggle, not `main`-only branch protection —
  chosen to avoid a `RAILWAY_TOKEN` secret; see Issues).
- `deployed.md` records: the public web URL, the `/health` shape, and a
  cold-start note (Hobby = always-on, no cold start; a sleeping free tier would
  add ~30-60 s to the first request and require no index rebuild).
- No paid database; SQLite file only. Secrets only via Railway variables.
- CI/CD (`.github/workflows/ci.yml`), triggers `push` and `pull_request` (no
  branch filter — CI runs on feature branches too):
  1. Install pinned `requirements.txt` (the exact set the image ships) + `pip install --no-deps -e .`.
  2. Import/start check: `python -c "import hr_agent.web.app"`.
  3. `ruff check .`.
  4. `python scripts/build_index.py --verify` (index determinism, offline).
  5. `pytest -q` — 140 tests, incl. MCP tool discovery + a real tool call, app
     start via `TestClient` + lifespan.
  6. `python -m evaluation.run_eval --smoke --offline` — the reduced eval
     subset, zero tokens.
  7. A separate `frontend` job: `npm ci && npm run build`.
  There is no explicit `deploy` job — Railway's Wait-for-CI watches the commit's
  check suite and holds/skips the platform-triggered deploy accordingly.

## Issues

Deviations are logged here as they're found, per phase. This section fell
behind after Phase 2 for several phases; the 2026-09-01 entry closes that gap.

### Phase 2 — real RAG + real MCP
- **`llm.py` surface.** The spec lists `complete(messages, tools=None)` / `classify(schema)` on a hand-rolled `google-genai` wrapper. Since orchestration uses a LangGraph `ToolNode`, `llm.py` instead exposes `chat_model()` returning a provider `BaseChatModel` (`ChatGroq` / `ChatGoogleGenerativeAI` / `ChatOpenAI`), so `bind_tools` / `AIMessage.tool_calls` / `tool_call_id` threading come normalized. The provider chat SDKs are imported only in `llm.py`, so the "provider is one config switch" rule still holds. `generate_answer()` (the string path) stays for the RAG-only fallback.
- **Confirmation gate.** Implemented as a two-call `pending_action` handshake (`confirm_gate` / `declined` nodes keyed off the emitted tool call), not `interrupt_before` + a checkpointer. **Resolved, not revisited:** sessions landed in Phase 3.5 and the handshake was kept as-is — it gives the same guarantee (no mock action runs without explicit `confirm: true`) with no checkpointer to configure or resume-wiring to get right. See Known risk (4), now closed.
- **MCP server module path.** The Folder Structure / Implementation sections specify `mcp/server.py` at the repo root, launched as `python -m mcp.server`. This shadows the installed `mcp` PyPI SDK — `sys.path` puts the repo root first (pytest's `pythonpath = ["."]` guarantees it), so `from mcp.server.fastmcp import FastMCP` resolves into the local folder and fails. Implemented instead as `src/hr_agent/mcp_server.py`, launched as `python -m hr_agent.mcp_server` (with `--http` for Streamable HTTP), all nine tools inline in one module rather than a `mcp/tools/` package. Railway start commands updated accordingly.
- **MCP tool signatures and behavior are simpler than planned throughout** — no `doc_filter` on search, `create_mock_hr_ticket`/`draft_hr_email` take fewer, flatter arguments. Full signatures: API section. *(Partly closed in Phase 8: `check_policy_compliance` is now retrieval-backed; the three thin tool returns were fleshed out.)*

### Phase 3 — deterministic gate + two demo workflows
- **`classify_intent` is deterministic, not an LLM node.** The agent node is already an LLM making a schema-constrained routing decision; a standalone classify call would mostly re-decide that, at the cost of one extra call into the same rate-limited budget on every `/chat`, a nondeterministic path every test must mock, and latency. The gate (`agent/gate.py`) instead uses signals already computed: employee-id resolution for `clarify`, a narrow ambiguity regex, and the vector-retrieval scope score for `guardrail_scope`. Deliberate; see `ai-tooling.md` and `build-note.md` §9d. *(Phase 8 added a fourth signal: an off-topic keyword deny-list for `guardrail_scope`.)*

### Phase 3.5 — UX pass, sessions
- **Frontend is plain JavaScript (`.jsx`), not TypeScript.** The Specifications and Folder Structure sections originally called for TypeScript/React with a multi-component tree (`ChatWindow.tsx`, `MessageList.tsx`, etc.); shipped as a single `App.jsx` in plain JS.
- **Sessions landed; the confirmation gate was not migrated to `interrupt_before`** (see the Phase 2 entry above — this is where that "revisit" was decided against).

### Phase 4–5 — deploy, CI/CD
- **One shared `Dockerfile`, not per-service Nixpacks/`uv` detection.** There is no `uv.lock` to detect (see the dependency-management entry below); both Railway services build the same image and differ only in start command.
- **`pip install -e .` (editable), not a plain install,** in the image — a non-editable install moves the package into `site-packages`, breaking `Path(__file__).parents[2]`-style lookups for `corpus/`, `mock_data/`, `data/`.
- **`--http` with no `--port` on the `mcp` start command** — Railway's Custom Start Command field is not shell-expanded, so `--port $PORT` would pass the literal string `$PORT`; the server reads `PORT` from the environment itself instead.
- **Deploy gate is Railway's per-service "Wait for CI" toggle, not a `deploy` job in the workflow.** Avoids managing a `RAILWAY_TOKEN` secret and a second failure surface; Railway holds/skips the platform-triggered deploy based on the commit's GitHub check-suite result. Verified live on the Phase 1–7 → `main` merge.
- **Dependencies stay on `pip` + `requirements.txt`, not `uv`/`uv.lock`.** Deliberate: the grading rubric accepts `requirements.txt`/`pyproject.toml` "as appropriate," a locked `uv.lock` was a vibespec-only goal worth zero rubric points, and `pip install -r requirements.txt` is exactly what the Dockerfile runs — CI exercises the same install path as the deploy artifact.
- **CI runs `ruff check` only, not `ruff format --check`.** The tree predates `ruff format` and enforcing it would churn ~22 hand-formatted files for no rubric gain. `[tool.ruff] line-length = 100` in `pyproject.toml` makes the lint config explicit instead.

### Phase 6 — evaluation harness
- **The harness drives the system in-process (`run_workflow`), not against a locally running pair of services.** The rubric requires reporting latency p50/p95, not a particular measurement method; this system's latency is dominated by the LLM tool-calling loop (3–56s observed), so HTTP/MCP-transport overhead is noise by comparison. In-process also keeps the suite deterministic and lets CI run a 6-item smoke subset with a stub model and zero tokens.
- **Groundedness judge context bug, found and fixed.** The judge was originally given only the post-run 220-char citation snippets (nothing at all for pure data-tool items), so it scored well-grounded answers "unsupported" — groundedness came back 0.29. Fixed by building the judge's context from the full text of the gold policy documents, and scoring groundedness only on items that have `gold_doc_ids`. Re-scored: 0.73. See `evaluation/run_eval.py:_context_for_judge`.
- **Judge-provider budget contention, found and fixed.** Gemini's judge-model free tier is 20 requests/day — too little for a 25-item run needing ~30 judge calls at two calls/item. Fix 1: `judge_combined()` scores groundedness and similarity in one call (~15 calls/run). Putting that one call on Groq instead shares Groq's daily token budget with the generator and starved it (12/25 items errored on one run); fix 2: `--rejudge <results.json>` re-scores a saved run's answers with no workflow re-run, so generation (the expensive, rate-limited half) is paid for once.
- **`ingest/builder.py` is legacy/dead code.** An earlier `build_index(corpus_dir, index_path)` that only globs `.md`/`.txt`; `scripts/build_index.py` calls `ingest.indexer.build_index(chunks, vectors, path)` instead. **Resolved (Phase 8):** deleted; `tests/test_ingestion.py` repointed at the real `chunk_corpus` → `indexer.build_index` path.
- **`HrTicket` mock-data shape vs. the live tool.** `mock_data/hr_tickets.json`'s committed sample rows match the originally planned `HrTicket` entity; the live `create_mock_hr_ticket` tool returned a simpler, hardcoded-`ticket_id` shape. **Resolved (Phase 8):** the tool now returns the sample-row shape with a deterministic `HR-<hash>` id; it still writes nothing to disk. See Data.

### Phase 7 — docs (this reconciliation)
- **This pass.** Every reference section above (Specifications, Architecture,
  Data, Folder Structure, Setup, UI, API, Database, Implementation, Testing,
  Deployment) was checked against the shipped code and corrected; the Change
  History, this Issues log, the Acceptance Criteria checkboxes, and the
  Glossary's confirmation-gate definition (it described a LangGraph interrupt
  that was never built) are now current as of 2026-09-01.

### Phase 8 — Tier 1 hardening (post-reconciliation)
- **Off-topic keyword pre-filter in the gate.** `gate.py` gains `looks_off_topic()`
  — a narrow deny-list (weather, sports scores, recipes, code-writing, general
  trivia, current events). A non-personal match routes to `guardrail_scope`
  regardless of retrieval score or method, closing the gap where an off-topic
  query pulled a real policy chunk above `SCOPE_THRESHOLD` and slipped through.
  Additive (explicit-match only), personal workflows exempt. Catches all 4 eval
  out-of-scope items, 0 false positives on the other 21.
- **`check_policy_compliance` is retrieval-backed.** Was a 3-branch keyword stub
  returning a bare `{status, message}`; now runs `retrieve()` for the top 3
  policy sections and returns them as `relevant_sections` evidence. The `status`
  stays a keyword-derived hint (widened to cover relocation / out-of-state /
  international remote / leave / termination / grievance), downgrading to
  `not_applicable` on empty retrieval. Still no LLM call.
- **Three thin tool returns fleshed out.** `create_mock_hr_ticket` → deterministic
  `HR-<sha1[:6]>` id + the `hr_tickets.json` sample-row shape; `draft_hr_email` →
  templated on topic + the employee's resolved first name; `list_policy_documents`
  → `[{doc_id, title}]` pairs. All still gated / read-only.
- **`ingest/builder.py` deleted**, `tests/test_ingestion.py` repointed at the real
  `chunk_corpus` → `indexer.build_index` pipeline.
- **CI action bumps** — `actions/checkout@v5`, `actions/setup-node@v5` (clears the
  Node 20 deprecation annotation).
- **`RETRIEVAL_K` 5 → 3** (config default + `.env.example`). Pulled forward from
  Tier 2 #8: the k-ablation shows citation F1 rises as k shrinks, and fewer
  passages means fewer tokens in every agent turn and in the gate scope check.
  The MCP `search_policy_documents` tool keeps its own `k=3` default.
- **`MAX_TOOL_ITERATIONS` 8 → 5.** The two demo workflows need ≤4 tool calls; 5
  leaves one turn of slack while capping what a wandering model can spend of the
  free-tier budget.
- **`run_eval --only <ids/categories>`** — run a gold-set subset (e.g. `--only
  straightforward,multi_doc` for the 11 citation-bearing items) to validate a
  change on one token-budget day; `RESULTS.md` is only regenerated on a full run.
- Test count 116 → 131. Judged-eval re-run to quantify the out-of-scope gain and
  confirm the k=3 citation-F1 improvement is deferred to its own token-budget day.

### Phase 9 — Tier 2 (citation precision + the tl-03 workflow miss)
- **Answer-aware citation selection.** Every policy-tool result row was collected
  as a citation, so the agent over-cited (baseline: recall 0.86 ≫ precision
  0.55). `compose` now keeps only the documents the answer actually names —
  `_answer_names_doc` matches the de-hyphenated doc-id stem against the answer
  text, since the model reliably writes prose names ("the PTO and Vacation
  Policy") rather than the `[doc-id]` markers the old prompt asked for. Falls
  back to the first ~4 in retrieval order when the answer names none, so a real
  answer never loses all citations. **Full 25-item judged run (2026-09-03, same
  Groq judge as the baseline):** citation **F1 0.64 → 0.86, precision
  0.55 → 0.89, recall unchanged at 0.86**; groundedness 0.73 → 0.85, similarity
  0.72 → 0.78; out-of-scope behavior 0.50 → 1.00; gate accuracy 0.75 → 1.00;
  action-safety held 1.00.
- **`tl-03` ("I'm E-1007. Who is my manager?")** — was a workflow-completion
  miss (fabricated PTO summary, similarity 0.0). Three changes:
  (a) `_AGENT_SYSTEM` rewritten with explicit per-tool "call X ONLY if …" rules
  and "answer only the question asked"; (b) `lookup_employee_profile` resolves
  `manager_name` so one call answers a manager question; (c) `_looks_unfinished`
  now also nudges filler that follows a tool call. In the full run `tl-03`
  scores **1.0** (fixed). `tl-05` (a tiered PTO-notice question the generator
  misreads as the 5-day tier) scored 1.0 in the baseline and 0.0 in this run —
  it reproduces the wrong answer under the *old* prompt too, so it is generator
  variance, not a Tier 2 regression. Net workflow completion 5/7 either way.
- **`_employee_hint`** no longer instructs the model to "use … for employee-data
  tools" (it read as a push to call tools).
- **`--rejudge` completion bug.** It updated judge scores but never recomputed
  the per-record `completed` flag, so the committed baseline `RESULTS.md`
  reported workflow completion as 6/7 when the honest figure from its own judge
  scores is 5/7. Fixed: `run_eval._mark_completed` is now shared by `run_item`
  and `--rejudge`.
- Test count 131 → 140.

### Known risks — status
1. **Free-tier LLM rate limits during the full 25-item eval.** *Materialized
   exactly as anticipated* — see the Phase 6 entries above. Mitigated with
   `judge_combined`, `--rejudge`, `--item-pace`, and retry/backoff; not fully
   closed — the tools-vs-RAG ablation is still pending a clean token budget.
2. **PDF heading inference for `06`/`09` might need a per-document override
   map.** Not needed in practice — both PDFs chunk and index successfully with
   the line-heuristic headings; no override map exists in the repo. Revisit if
   a future corpus PDF chunks badly.
3. **Committing a binary `index.sqlite`.** Unchanged, accepted: guarded by the
   CI determinism check (`build_index.py --verify` on every push).
4. **`LangGraph interrupt_before` needs a checkpointer and resume wiring.**
   *Closed* — the confirmation gate was never migrated to `interrupt_before`
   (see the Phase 2/3.5 entries); the two-call handshake is the permanent
   design.

## Glossary
- **RAG**: Retrieval-Augmented Generation — retrieving relevant text chunks and injecting them into the LLM prompt so answers are grounded in a known corpus.
- **MCP**: Model Context Protocol — a standard for exposing tools/resources to an LLM agent. Here, a separate service exposes nine tools the agent discovers and calls.
- **Streamable HTTP**: the MCP transport used in production (HTTP with streamed responses), as opposed to stdio (spawned subprocess) used for local single-process dev.
- **Operational trace**: a concise, structured log of what the agent did (intent, retrieval, tool calls/results, confirmation, escalation, answer basis) — deliberately not chain-of-thought.
- **Confirmation gate**: a two-call `pending_action` handshake (not a LangGraph interrupt — see Issues) that pauses before any mock action; the run stops and returns the proposed action, and the client must re-POST with `confirm: true` to execute it or `confirm: false` to drop it.
- **Groundedness**: the degree to which every claim in an answer is supported by the retrieved context.
- **Ablation**: re-running the system with one variable changed (e.g., retrieval k) to measure its effect.
- **Northwind Robotics, Inc.**: the fictional ~650-employee robotics company whose synthetic policies and data this system serves.

## References

### Related
- [vibespec instructions](./vibespec-instructions.md)
- [vibespec structure outline](./structure.md)
- [design-and-evaluation.md](./design-and-evaluation.md) — rubric-facing rendering of Architecture, Data, API, Implementation, Testing, Deployment + evaluation results — done, Phase 7
- [ai-tooling.md](./ai-tooling.md) — describes use of vibespec + Claude Code — done, Phase 7
- [deployed.md](./deployed.md) — deployed URLs + cold-start notes — done, Phase 4

### External
- Project brief: Quantic "AI Engineering Techniques and Architectures" project (PDF provided by the course).
- vibespec: https://github.com/joeax/vibespec
- Model Context Protocol: https://modelcontextprotocol.io
- LangGraph: https://langchain-ai.github.io/langgraph/
- Google Gemini API: https://ai.google.dev/
- Groq API: https://console.groq.com/
- sqlite-vec: https://github.com/asg017/sqlite-vec
- Railway: https://railway.app/
