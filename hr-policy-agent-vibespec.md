# HR Policy & Operations Agent

This is a vibespec. It describes an agentic AI assistant that helps employees of a hypothetical company (Northwind Robotics, Inc.) complete HR policy and operations tasks. The system combines Retrieval-Augmented Generation (RAG) over a corpus of internal policy documents with an agent orchestrator that plans, selects tools, calls one or more Model Context Protocol (MCP) servers, reads mock structured data (employee records, PTO balances, benefits elections), and produces grounded, cited responses with a concise operational trace. It is built for the Quantic "AI Engineering Techniques and Architectures" course project and is graded against that project's rubric.

## About
- version: 0.1.0
- author: Candace Wilson
- last updated: 2026-08-29

## Change History
- 2026-08-29: Initial version. Captures all planning decisions prior to any code generation.

## Specifications
- type: full-stack web app with a React frontend and a Python FastAPI backend, plus a companion MCP service
- languages: Python 3.12 (backend + agent orchestration), TypeScript/React 19 (frontend)
- frameworks: React + TypeScript + Vite (frontend), FastAPI (web + API), LangGraph (agent orchestration), FastMCP / official Python MCP SDK (MCP server), langchain-mcp-adapters (MCP client wiring), sqlite-vec (vector store)
- target platform: Linux container on Railway (Hobby tier); also runs locally on macOS/Linux
- LLM provider: Google Gemini (model `gemini-2.0-flash`) via `google-genai`
- embedding provider: Google Gemini `text-embedding-004`
- package managers: `uv` for the Python backend and `npm`/`pnpm`/`yarn` for the React frontend (pick one and lock it)

### Dependencies
- python 3.12 (pinned via `.python-version`)
- uv (latest)
- fastapi
- uvicorn[standard]
- google-genai
- langgraph
- langchain-core
- langchain-mcp-adapters
- mcp (official Python MCP SDK) / fastmcp
- sqlite-vec
- pydantic v2
- markdown-it-py (markdown parsing for ingestion)
- beautifulsoup4 (HTML parsing for ingestion)
- pypdf (PDF parsing for ingestion)
- tiktoken (token counting for deterministic chunking)
- httpx (MCP Streamable HTTP client/server transport)
- python-dotenv (local env loading)
- pytest, pytest-asyncio (tests)
- ruff (lint)
- rouge-score (evaluation: partial-match scoring)

All version pins are resolved and locked in `uv.lock`. Exact minimum versions are chosen at Phase 0 and recorded there.

## Features
- Policy question answering grounded in an indexed corpus of company policy documents, with inline citations (document id, title, section) and supporting snippets.
- Multi-document retrieval for complex questions that span several policies.
- Guardrails that refuse or redirect out-of-corpus and non-HR questions, limit unsupported claims, and separate stated policy from recommendations.
- An agent orchestrator that interprets intent, decides whether RAG alone suffices, selects and calls MCP-exposed tools, handles failures, and synthesizes a final response.
- At least five multi-step HR workflows: remote-work eligibility, PTO request guidance, expense compliance, benefits triage, and HR case triage. Two are the deployed demo tasks (remote-work eligibility, PTO request guidance).
- An MCP server exposing nine tools over Streamable HTTP; the agent discovers tools at runtime and calls them for real (no hard-coded direct function calls).
- Confirmation-gated mock actions: creating a mock HR ticket or drafting an HR email pauses for explicit user confirmation and never performs an irreversible action.
- A concise, logged operational trace of each request: intent, retrieved sources, tool calls with arguments, tool results, answer basis, and any escalation decision. No hidden chain-of-thought is exposed.
- A chat web UI with collapsible Citations and Tool Trace panels, confirm/deny controls, and one-click demo-task presets.
- A `/health` endpoint reporting app status, MCP connectivity, and vector-store status.
- An evaluation harness of 25 questions/tasks across five categories, reporting answer-quality, agent-behavior, and system metrics, plus at least one ablation.
- CI/CD via GitHub Actions: lint, tests (including MCP tool discovery and a tool call), and deploy only on green.

## Requirements

Functional:
- Ingest a corpus of 12 policy documents in at least two source formats (this project uses three: Markdown, PDF, HTML), clean them, and chunk them with a deterministic heading-aware strategy.
- Embed chunks with a free-tier embedding model and store them with metadata sufficient for citation (document id, title, section path, source snippet, source format, chunk index).
- Provide top-k retrieval (default k = 5) with optional document filtering and optional LLM query rewriting.
- Inject retrieved chunks plus source metadata into the LLM prompt; generate answers that cite document ids/titles/sections and include supporting snippets.
- Include at least one question that requires retrieval from multiple documents (remote-work eligibility spans Remote & Hybrid Work, Out-of-State & International Remote Work, and Data Security policies).
- Provide an agent orchestrator (LangGraph custom graph) that classifies intent, routes to clarification / scope-refusal / agent execution, loops over tool calls, gates destructive actions, and composes a grounded final answer.
- Support at least two multi-step workflows end-to-end; build and evaluate five.
- Emit a structured operational trace for every `/chat` request and return it in the response and render it in the UI.
- Handle failures gracefully: unavailable MCP tool/server (degrade to RAG-only with a caveat), unknown employee id (ask the user to confirm), insufficient policy evidence (state uncertainty, recommend HR, set escalation flag), ambiguous request (ask one clarifying question), tool-loop cap (stop and answer with what was gathered).
- Expose an MCP server with nine tools: `search_policy_documents`, `get_policy_section`, `list_policy_documents`, `check_policy_compliance`, `lookup_employee_profile`, `check_pto_balance`, `lookup_benefits_status`, `create_mock_hr_ticket`, `draft_hr_email`. At least one tool uses the RAG index (four do); at least one uses mock structured data or performs a mock operation (five do).
- The agent must discover MCP tools at runtime and invoke them through the MCP layer.
- Provide a `/chat` endpoint returning final answer, citations, snippets, and a concise tool-call trace; a `/health` endpoint returning JSON status including MCP connectivity; and a way for a grader to reproduce the two demo tasks from the UI.
- Provide an evaluation set of 25 items covering straightforward policy Q&A, multi-document questions, tool-requiring tasks, ambiguous requests, and out-of-scope requests, each with gold answers / expected behavior. Report groundedness, citation accuracy, optional partial match, tool-selection accuracy, workflow-completion rate, escalation/clarification accuracy, action-safety pass rate, and latency p50/p95. Include at least one ablation (retrieval k, chunk size, and tools-enabled vs RAG-only).

Non-functional:
- Reproducibility: `uv.lock`, pinned Python version, deterministic chunking (byte-identical chunks for identical input), fixed `SEED` for any evaluation sampling. The built vector index is committed as a deterministic artifact and rebuilt+verified in CI.
- Cost: zero LLM/embedding cost via Gemini free tier; hosting on Railway Hobby (already owned). No paid database.
- Latency target: warm p50 under ~6 s and warm p95 under ~15 s for representative tasks on free-tier models; measured and reported, not guaranteed.
- Portability: the entire system runs locally with `uv run` and two processes (web + MCP), or MCP over stdio for single-process local dev.

Security:
- All secrets (`GEMINI_API_KEY`, any deploy tokens) are read from environment variables / Railway variables and never committed. `.env` is git-ignored; `.env.example` lists every variable.
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
- Swap the embedding/LLM provider via config only (provider abstraction already isolates `google-genai` calls).
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
5. `tools` node executes each MCP tool call, appends `tool_call` and `tool_result` entries to the trace, and captures citations from policy tools.
6. If a destructive tool (`create_mock_hr_ticket` or `draft_hr_email`) is pending, `confirm_gate` interrupts: the UI shows the proposed action with confirm/deny controls. On confirm, execution resumes; on deny, the action is dropped and noted in the trace.
7. The `agent` <-> `tools` loop repeats until no tool calls remain or the iteration cap (8) is hit.
8. `compose_answer` synthesizes a grounded answer: inline `[doc_id]` markers, snippets, a "What the policy says" vs "Suggested next steps" split, and an insufficient-evidence fallback that sets the escalation flag.
9. `finalize` assembles the response: `answer`, `citations`, `snippets`, `trace`, `escalation`, and optional `pending_action`.
10. The UI renders the answer, the Citations panel, and the Tool Trace panel.

### Acceptance Criteria
- [ ] A plain policy question returns an answer with at least one correct citation to the source document and section.
- [ ] The remote-work eligibility task retrieves from at least two distinct policy documents and calls `lookup_employee_profile` and `check_policy_compliance` before answering.
- [ ] The PTO request task calls `check_pto_balance`, retrieves the PTO policy, and does not create a ticket or draft an email until the user confirms.
- [ ] An out-of-scope question is refused/redirected without fabricating a policy answer.
- [ ] An ambiguous question yields exactly one clarifying question rather than a guess.
- [ ] Every `/chat` response includes a non-empty `trace` array whose entries name the tools called, their argument summaries, and result summaries.
- [ ] `/health` returns JSON with `status`, `mcp.connected`, `mcp.tools_discovered` (>= 5), and `vector_store.loaded`.
- [ ] The agent obtains its tool list via MCP discovery at runtime; removing the MCP server causes `/health` to report `mcp.connected = false` and the agent to degrade to RAG-only with a caveat.
- [ ] CI fails if any test fails, and deployment does not run unless CI is green.
- [ ] `uv run python scripts/build_index.py --verify` reports identical chunk count and content hash on two consecutive runs.
- [ ] The evaluation harness produces `evaluation/RESULTS.md` with all required metrics and at least one ablation table.

## Architecture

The system is two deployable services built from one monorepo, plus a build-time ingestion pipeline.

```
                          +-------------------------------------------------+
                          |  Browser: React + TypeScript chat app           |
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
|   LangGraph custom graph:                                                              |
|     classify_intent -> [ clarify | guardrail_scope | agent ]                           |
|     agent  <->  tools (ToolNode)                                                       |
|     tools  ->  confirm_gate (interrupt_before destructive tools)  ->  agent            |
|     agent  ->  compose_answer  ->  finalize                                            |
|                                                                                       |
|   MCP client (langchain-mcp-adapters): discovers tools, adapts them to LangGraph tools |
|   LLM client (google-genai): classify, agent reasoning, compose, eval judge            |
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
   corpus/*.{md,pdf,html}  ->  ingest pipeline (load -> clean -> chunk -> embed -> index)
                           ->  data/index/index.sqlite  (committed, deterministic; CI rebuilds and verifies)
```

Patterns:
- Facade: `mcp_client` exposes a single `get_tools()` / `call_tool()` surface over the MCP transport.
- Dependency injection via config: LLM model, embedding model, retrieval k, chunk size/overlap, seed, and `MCP_SERVER_URL` are all injected from `config.py` (env-backed) so no provider or size choice is hard-coded.
- Separation of concerns: web/API, orchestration (graph), MCP client, MCP server + tools, RAG index, and mock data are distinct modules; the LLM provider is isolated behind a thin wrapper.
- Interrupt / human-in-the-loop: LangGraph `interrupt_before` on destructive tool nodes implements the confirmation gate.
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
- doc_id: string (references PolicyDocument)
- doc_title: string
- section_path: string (e.g. `Eligibility > Approval`)
- chunk_index: integer
- source_format: string
- char_span: [integer, integer] (offsets into the cleaned document)
- text: string
- embedding: float32[768] (Gemini `text-embedding-004`)

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

### Relationships
- PolicyDocument has a one-to-many relationship with PolicyChunk.
- Employee has a one-to-one relationship with PtoBalance and with BenefitsElection.
- Employee has a many-to-one self relationship via `manager_id`.
- Employee has a many-to-one relationship with OfficeLocation.
- Employee has a one-to-many relationship with HrTicket (mock, session-scoped).

## Folder Structure
```
hr-policy-agent/
├── README.md
├── design-and-evaluation.md
├── ai-tooling.md
├── deployed.md
├── CLAUDE.md
├── hr-policy-agent-vibespec.md
├── vibespec-instructions.md
├── structure.md
├── pyproject.toml
├── uv.lock
├── .python-version
├── .env.example
├── .gitignore
├── ruff.toml
├── .github/
│   └── workflows/
│       └── ci.yml
├── corpus/
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
│   └── 12-workplace-conduct-and-grievance-procedure.html
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
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── index.css
│   │   ├── api.ts
│   │   ├── types.ts
│   │   └── components/
│   │       ├── ChatWindow.tsx
│   │       ├── MessageList.tsx
│   │       ├── CitationPanel.tsx
│   │       ├── TracePanel.tsx
│   │       └── DemoButtons.tsx
├── src/
│   └── hr_agent/
│       ├── __init__.py
│       ├── config.py
│       ├── seeds.py
│       ├── llm.py                 # google-genai wrapper (chat + embeddings)
│       ├── ingest/
│       │   ├── loaders_md.py
│       │   ├── loaders_html.py
│       │   ├── loaders_pdf.py
│       │   ├── cleaner.py
│       │   ├── chunker.py
│       │   ├── embedder.py
│       │   └── indexer.py
│       ├── rag/
│       │   ├── retriever.py
│       │   ├── prompts.py
│       │   ├── guardrails.py
│       │   └── citations.py
│       ├── agent/
│       │   ├── graph.py
│       │   ├── state.py
│       │   ├── nodes.py
│       │   └── trace.py
│       ├── mcp_client/
│       │   └── discovery.py
│       └── web/
│           ├── app.py
│           └── sessions.py
├── mcp/
│   ├── server.py
│   ├── README.md
│   └── tools/
│       ├── policy.py              # search_policy_documents, get_policy_section, list_policy_documents
│       ├── compliance.py          # check_policy_compliance
│       ├── employees.py           # lookup_employee_profile
│       ├── pto.py                 # check_pto_balance
│       ├── benefits.py            # lookup_benefits_status
│       ├── actions.py             # create_mock_hr_ticket, draft_hr_email
│       └── schemas.py             # pydantic input/output models for all tools
├── evaluation/
│   ├── eval_questions.jsonl
│   ├── run_eval.py
│   ├── judges.py                  # LLM-judge: groundedness, partial match
│   ├── ablation.py
│   ├── RESULTS.md
│   └── results/
│       └── .gitkeep
├── tests/
│   ├── conftest.py
│   ├── test_app.py
│   ├── test_ingestion.py
│   ├── test_mcp.py
│   ├── test_rag.py
│   └── test_agent_safety.py
└── scripts/
    ├── build_index.py
    ├── run_local.sh
    └── run_mcp_local.sh
```

## Setup
- Install `uv` (https://docs.astral.sh/uv/). Confirm `uv --version`.
- Install the Python dependencies: from the repo root, run `uv sync` to create `.venv/` and install locked dependencies.
- Install the frontend dependencies: from the `frontend/` directory, run `npm install` (or `pnpm install` / `yarn install` if the project chooses a different package manager).
- Copy `.env.example` to `.env` and set `GEMINI_API_KEY`. Leave `MCP_SERVER_URL` unset for single-process local dev (the web app will spawn the MCP server over stdio), or set it to `http://127.0.0.1:8765/mcp` to run the MCP server as a separate local process.
- Build the vector index: `uv run python scripts/build_index.py`. The committed `data/index/index.sqlite` is already valid; rebuild only after changing the corpus or chunking config.
- Run the MCP server (separate-process mode): `bash scripts/run_mcp_local.sh` (starts FastMCP Streamable HTTP on port 8765).
- Run the backend: `bash scripts/run_local.sh` (starts uvicorn on port 8000).
- Run the React frontend: `cd frontend && npm run dev` (Vite default port 5173). Open http://127.0.0.1:5173.
- For a single-host local demo, the frontend can proxy API calls to the FastAPI backend at `http://127.0.0.1:8000`.

Environment variables (see `.env.example`):
- `GEMINI_API_KEY` (required)
- `LLM_MODEL` (default `gemini-2.0-flash`)
- `EMBEDDING_MODEL` (default `text-embedding-004`)
- `MCP_SERVER_URL` (optional; when set, web app uses Streamable HTTP instead of stdio)
- `MCP_PORT` (default `8765`, MCP service only)
- `RETRIEVAL_K` (default `5`)
- `CHUNK_SIZE` (default `800` tokens)
- `CHUNK_OVERLAP` (default `120` tokens)
- `SEED` (default `42`)
- `MAX_TOOL_ITERATIONS` (default `8`)

### Validation
- `uv run ruff check` completes with no errors.
- `uv run pytest` passes.
- `uv run python scripts/build_index.py --verify` reports identical chunk count and content hash across two runs.
- `curl localhost:8000/health` returns JSON with `status: "ok"`, `mcp.connected: true`, `mcp.tools_discovered: 9`, `vector_store.loaded: true`.
- In the UI, the two demo presets (remote-work eligibility, PTO request) each complete end-to-end, showing tool calls in the Trace panel and at least one citation.

## UI

A React + TypeScript single-page chat interface that talks to the Python FastAPI backend. The frontend is a Vite app under `frontend/` and renders all conversational, citation, and trace views from API responses.

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
- **GET /** : Serves the static chat page.
- **POST /chat** : Body `{ "message": string, "employee_id"?: string, "session_id"?: string, "confirm"?: boolean }`. Returns:
  ```
  {
    "session_id": string,
    "answer": string,
    "citations": [ { "doc_id": string, "title": string, "section": string, "snippet": string } ],
    "trace": [ { "step": int, "type": string, "name"?: string, "args_summary"?: string,
                 "result_summary"?: string, "sources"?: [string] } ],
    "escalation": boolean,
    "pending_action"?: { "tool": string, "args_summary": string, "description": string }
  }
  ```
  When `pending_action` is present, the client re-calls `POST /chat` with the same `session_id` and `confirm: true` (or `confirm: false` to cancel).
- **GET /health** : Returns:
  ```
  {
    "status": "ok",
    "version": string,
    "mcp": { "connected": boolean, "tools_discovered": int, "transport": "streamable_http" | "stdio" },
    "vector_store": { "loaded": boolean, "chunks": int }
  }
  ```

### MCP tool interface (Service B, not HTTP REST)
Discovered via MCP `list_tools`. Each tool has a Pydantic input schema and returns a typed JSON object (errors are returned as `{ "error": "<code>", "message": "<text>" }`, never raised across the wire).

- `search_policy_documents(query: str, top_k: int = 5, doc_filter: list[str] | None = None)` -> `{ "results": [ { "doc_id", "title", "section", "snippet", "score" } ] }`
- `get_policy_section(doc_id: str, section: str)` -> `{ "doc_id", "title", "section", "text" }` or `{ "error": "not_found" }`
- `list_policy_documents()` -> `{ "documents": [ { "doc_id", "title", "summary" } ] }`
- `check_policy_compliance(scenario: str, employee_id: str | None = None)` -> `{ "decision": "allowed" | "conditional" | "not_allowed" | "needs_review", "conditions": [str], "required_approvals": [str], "citations": [ { "doc_id", "section" } ] }`
- `lookup_employee_profile(employee_id: str)` -> Employee object or `{ "error": "unknown_employee" }`
- `check_pto_balance(employee_id: str)` -> PtoBalance object (+ derived `available_hours`) or `{ "error": "unknown_employee" }`
- `lookup_benefits_status(employee_id: str)` -> BenefitsElection object or `{ "error": "unknown_employee" }`
- `create_mock_hr_ticket(employee_id: str, category: str, summary: str, details: str)` -> `{ "ticket_id", "status": "created_mock", "category", "created_at" }` (confirmation-gated by the orchestrator)
- `draft_hr_email(employee_id: str, purpose: str, context: str)` -> `{ "draft_subject", "draft_body" }` (confirmation-gated; never sends)

## Database
No relational database. Storage is:
- `data/index/index.sqlite` : a SQLite file with the `sqlite-vec` extension. One virtual table `vec_chunks(embedding float[768])` plus a companion table `chunks(chunk_id TEXT PRIMARY KEY, doc_id, doc_title, section_path, chunk_index, source_format, char_start, char_end, text)`. Loaded read-only by both services. Committed to the repo as a deterministic build artifact; `data/index/manifest.json` records chunk count, SHA-256 of concatenated chunk texts, chunk size/overlap, embedding model, and build timestamp.
- `mock_data/*.json` : synthetic structured data, loaded read-only. `create_mock_hr_ticket` writes only to an in-process copy of the ticket list (optionally flushed to a temp file), never to the committed `hr_tickets.json`.
- Sessions and traces: in-memory dict in the web service, keyed by `session_id`. Not persisted (see Future Considerations).

## Implementation

### Services
- **web (`src/hr_agent/web/app.py`)**: FastAPI app. Startup: load config, load `data/index/manifest.json` for `/health` stats, initialize the MCP client (discover tools), compile the LangGraph graph. Routes: `/`, `/chat`, `/health`. Shutdown: close MCP client / terminate stdio subprocess.
- **mcp (`mcp/server.py`)**: FastMCP server exposing the nine tools. Startup: load the sqlite-vec index and the mock JSON. Transport: Streamable HTTP on `MCP_PORT` in production and separate-process local dev; stdio when spawned by the web app.

### Modules
- `config.py`: a frozen Pydantic `Settings` object built from environment variables with the defaults listed in Setup.
- `seeds.py`: sets `random.seed(SEED)` and any library seeds; used by evaluation sampling and anywhere nondeterminism could enter (chunking itself is deterministic by construction).
- `llm.py`: thin wrapper over `google-genai` exposing `complete(messages, tools=None)`, `classify(schema)`, and `embed(texts)`; the only file that imports the provider SDK.

### Ingestion (`src/hr_agent/ingest/`)
- `loaders_md.py` / `loaders_html.py` / `loaders_pdf.py`: parse a source file into `(cleaned_text, heading_tree)` where each heading node has a title, level, and char span. Markdown via `markdown-it-py`; HTML via `beautifulsoup4` (extract headings + text, drop nav/script/style); PDF via `pypdf` (page text; headings inferred from line heuristics and a per-document override map if needed).
- `cleaner.py`: normalize whitespace, strip repeated headers/footers, keep section anchors.
- `chunker.py`: deterministic heading-aware chunking. Walk the heading tree; within each leaf section, pack sentences into windows of `CHUNK_SIZE` tokens (tiktoken count) with `CHUNK_OVERLAP` token overlap; never split a sentence; carry `section_path` (breadcrumb of ancestor headings). Output ordered `PolicyChunk` records with stable `chunk_index` and `char_span`. Identical input + config yields byte-identical chunks.
- `embedder.py`: batch-embed chunk texts via `llm.embed`.
- `indexer.py`: create/replace `index.sqlite`, insert chunks + vectors, write `manifest.json`. `--verify` mode rebuilds to a temp file and compares chunk count + content hash to the committed manifest.

### RAG (`src/hr_agent/rag/`)
- `retriever.py`: `retrieve(query, k, doc_filter=None)` -> embed query, sqlite-vec KNN, optional `doc_id` filter, return chunks with scores. Optional `rewrite_query(query, history)` using the LLM (toggled by an ablation flag).
- `prompts.py`: system prompt and the answer-composition prompt (answer only from context; mark each factual sentence with `[doc_id]`; separate "What the policy says" from "Suggested next steps"; if context is insufficient, say so and recommend contacting HR).
- `guardrails.py`: `is_in_scope(query)` classifier (HR/policy/operations vs not) and the refusal/redirect text; helper to flag recommendations vs stated policy.
- `citations.py`: dedupe and format citations from retrieved chunks and from `check_policy_compliance` / `get_policy_section` results.

### Agent (`src/hr_agent/agent/`)
- `state.py`: `AgentState` TypedDict — `messages`, `user_query`, `session_id`, `employee_id` (optional), `intent`, `retrieved` (chunks), `citations`, `tool_trace` (list of dicts), `pending_action` (optional), `escalation` (bool), `final_answer` (optional).
- `nodes.py`:
  - `classify_intent`: LLM structured output -> `intent` + optional `employee_id`.
  - `clarify`: returns one clarifying question; sets `final_answer`; ends.
  - `guardrail_scope`: returns refusal/redirect; sets `final_answer`; ends.
  - `agent`: LLM bound to the MCP-derived tools; decides RAG-only vs tool calls; may call `search_policy_documents` directly for `policy_qa`.
  - `tools`: LangGraph `ToolNode` over the adapted MCP tools; appends `tool_call` / `tool_result` trace entries; collects citations.
  - `confirm_gate`: `interrupt_before` for `create_mock_hr_ticket` and `draft_hr_email`; sets `pending_action`; on resume with `confirm=true` proceeds, with `confirm=false` drops the action and adds a `confirmation` trace entry.
  - `compose_answer`: LLM synthesis per `prompts.py`; sets `escalation` when evidence is insufficient.
  - `finalize`: assembles the response payload from state.
- `graph.py`: builds and compiles the StateGraph with the edges in User Flow; configures the checkpointer needed for `interrupt_before`; exposes `run(session_id, message, employee_id, confirm)`.
- `trace.py`: helpers to append normalized trace entries and to redact anything resembling chain-of-thought (only operational fields are stored: step, type, name, args_summary, result_summary, sources).

### MCP client (`src/hr_agent/mcp_client/`)
- `discovery.py`: builds a `MultiServerMCPClient` (langchain-mcp-adapters). If `MCP_SERVER_URL` is set -> Streamable HTTP; else -> stdio spawning `python -m mcp.server`. Exposes `get_tools()` (LangGraph-compatible) and `health()` (connected?, tool count, transport).

### MCP tools (`mcp/tools/`)
- `schemas.py`: Pydantic models for every tool input and output.
- `policy.py`: `search_policy_documents` and `list_policy_documents` use `retriever` / the doc catalog; `get_policy_section` reads section text from the index by `doc_id` + `section_path`.
- `compliance.py`: `check_policy_compliance` retrieves scenario-relevant chunks, optionally loads the employee profile, and asks the LLM for a structured decision with citations.
- `employees.py`, `pto.py`, `benefits.py`: load and return records from `mock_data/`; typed `unknown_employee` error.
- `actions.py`: `create_mock_hr_ticket` (append to in-process list, return generated id) and `draft_hr_email` (LLM drafts subject + body from `purpose` + `context`; returns text only).

### Web (`src/hr_agent/web/`)
- `app.py`: FastAPI routes and lifespan wiring described under Services.
- `sessions.py`: in-memory session store with message history and any `pending_action`; `session_id` generated if absent.
- `static/`: `index.html`, `app.js` (fetch to `/chat`, render answer + panels + confirm/deny), `style.css`.

### Scripts (`scripts/`)
- `build_index.py`: run the full ingestion pipeline; `--verify` for the determinism check.
- `run_local.sh`: `uv run uvicorn hr_agent.web.app:app --port 8000 --reload`.
- `run_mcp_local.sh`: `uv run python -m mcp.server --http --port 8765`.

## Testing

### Unit Tests
- `test_ingestion.py`:
  - Chunking is deterministic: chunk a fixture document twice; assert identical chunk count and identical concatenated-text SHA-256.
  - Heading-aware behavior: a fixture with nested headings yields chunks whose `section_path` matches the expected breadcrumbs and never splits a sentence.
  - Multi-format loaders: a small `.md`, `.html`, and `.pdf` fixture each load to non-empty cleaned text with at least one heading.
- `test_rag.py`:
  - Retrieval relevance: query "how much PTO do I accrue" returns a top chunk whose `doc_id` is `pto-and-vacation-policy`.
  - Guardrail: `is_in_scope("what's the weather tomorrow")` is false; `is_in_scope("can I expense a monitor")` is true.
  - Citation formatting: dedupes chunks from the same section into one citation with a snippet.
- `test_agent_safety.py`:
  - Confirm gate: a PTO-request run that would call `create_mock_hr_ticket` stops with a `pending_action` and no ticket in the in-process list; resuming with `confirm=false` leaves no ticket and adds a `confirmation` trace entry; resuming with `confirm=true` creates exactly one mock ticket.
  - Trace shape: every run produces a `trace` list whose entries only contain the allowed operational fields.
  - Unknown employee: a workflow with `employee_id="E-9999"` yields a clarifying/redirect response, not a fabricated profile.

### Integration Tests
- `test_mcp.py`:
  - Tool discovery: start the MCP server (stdio), connect the client, assert exactly nine tools with the expected names and that each has a non-empty input schema.
  - Tool call: call `list_policy_documents` and assert it returns 12 documents; call `check_pto_balance("E-1007")` and assert a numeric `available_hours`.
  - Degradation: with the MCP client pointed at an unreachable URL, `discovery.health()` reports `connected=false` and the graph still returns a RAG-only answer with a caveat.
- `test_app.py`:
  - App starts: FastAPI `TestClient` boots; `GET /health` returns 200 with the documented shape and `mcp.tools_discovered >= 5`.
  - `POST /chat` smoke: a plain policy question returns 200 with a non-empty `answer`, at least one citation, and a non-empty `trace`.

### End-to-End Tests
- Covered by the evaluation harness (`evaluation/run_eval.py`) run against a locally running pair of services: the 25-item set exercises all five categories and the two demo tasks end-to-end, and `RESULTS.md` is regenerated. A CI job runs a reduced 6-item smoke subset to keep runtime and token use bounded; the full run is executed locally and its results are committed.

Evaluation metrics (reported in `evaluation/RESULTS.md`):
- Answer quality: groundedness (LLM-judge, 0-1), citation accuracy (precision/recall/F1 of returned `doc_id`s vs gold), partial match (ROUGE-L + LLM-judge similarity vs short gold answers).
- Agent behavior: tool-selection accuracy (Jaccard of actual vs expected tools), workflow-completion rate, escalation/clarification accuracy, action-safety pass rate.
- System: latency p50/p95 over the 25 items plus a 10-query warm run; cold vs warm noted (Railway Hobby is always warm).
- Ablation: retrieval k in {2, 4, 8}; chunk size in {500, 800, 1200}; tools-enabled vs RAG-only on the 7 workflow items. Results as tables with a short written analysis.

## Deployment
- Deployment environment: Railway (Hobby tier), two services from one GitHub repo.
  - Service A `web`: start command `uv run uvicorn hr_agent.web.app:app --host 0.0.0.0 --port $PORT`. Public HTTPS domain. Variables: `GEMINI_API_KEY`, `LLM_MODEL`, `EMBEDDING_MODEL`, `MCP_SERVER_URL=http://<service-b-domain>.railway.internal:${MCP_PORT}/mcp`, `RETRIEVAL_K`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `SEED`, `MAX_TOOL_ITERATIONS`.
  - Service B `mcp`: start command `uv run python -m mcp.server --http --host 0.0.0.0 --port $PORT`. Private networking only. Variables: `GEMINI_API_KEY`, `EMBEDDING_MODEL`, `RETRIEVAL_K`, `MCP_PORT`.
- Both services build with Railway's Nixpacks/`uv` detection from `pyproject.toml` + `uv.lock`; the committed `data/index/index.sqlite` and `mock_data/` ship in the image, so no build-time embedding calls are needed.
- Railway is configured to deploy only after the GitHub Actions CI checks pass ("Wait for CI" / branch protection on `main`).
- `deployed.md` records: the public web URL, the `/health` URL, and a cold-start note (Hobby = always-on, no cold start; a sleeping free tier would add ~30-60 s to the first request and require no index rebuild).
- No paid database; SQLite file only. Secrets only via Railway variables.
- CI/CD (`.github/workflows/ci.yml`), triggers `push` and `pull_request`:
  1. `lint`: `uvx ruff check`.
  2. `test`: `uv sync`; `uv run pytest` (unit + integration, including MCP tool discovery and a tool call); `uv run python scripts/build_index.py --verify`; reduced eval smoke subset.
  3. `deploy`: `needs: [lint, test]`, only on `push` to `main`; triggers the Railway deployment (Railway GitHub integration with wait-for-CI, or `railway up` via CLI using `RAILWAY_TOKEN` secret). Deployment does not run if `lint` or `test` fails.

## Issues
- **Deviation (Phase 2): `llm.py` surface.** The spec lists `complete(messages, tools=None)` / `classify(schema)` on a hand-rolled `google-genai` wrapper. Since orchestration uses a LangGraph `ToolNode`, `llm.py` instead exposes `chat_model()` returning a provider `BaseChatModel` (`ChatGroq` / `ChatGoogleGenerativeAI` / `ChatOpenAI`), so `bind_tools` / `AIMessage.tool_calls` / `tool_call_id` threading come normalized. The provider chat SDKs are imported only in `llm.py`, so the "provider is one config switch" rule still holds. `generate_answer()` (the string path) stays for the RAG-only fallback.
- **Deviation (Phase 2): confirmation gate.** Implemented as a two-call `pending_action` handshake (`confirm_gate` / `declined` nodes keyed off the emitted tool call), not `interrupt_before` + a checkpointer — `/chat` is stateless and has no session store yet. Same guarantee (no mock action runs without explicit `confirm: true`). Revisit `interrupt_before` when sessions land.
- **Deviation (Phase 2): MCP server module path.** The Folder Structure / Implementation sections specify `mcp/server.py` at the repo root, launched as `python -m mcp.server`. This shadows the installed `mcp` PyPI SDK — `sys.path` puts the repo root first (pytest's `pythonpath = ["."]` guarantees it), so `from mcp.server.fastmcp import FastMCP` resolves into the local folder and fails. Implemented instead as `src/hr_agent/mcp_server.py`, launched as `python -m hr_agent.mcp_server` (with `--http` for Streamable HTTP). Update the Railway start commands accordingly (`python -m hr_agent.mcp_server` / `python -m hr_agent.mcp_server --http --port $PORT`).
- None yet; no code generated. This section will list concrete defects (file and symptom) as they are found during phase-by-phase generation and review.
- Known risks to watch: (1) free-tier Gemini rate limits during the full 25-item eval — mitigate with request pacing and a reduced CI subset; (2) PDF heading inference may need a per-document override map for `06` and `09`; (3) committing a binary `index.sqlite` — acceptable per the project brief ("committed synthetic data files") and guarded by the CI determinism check; (4) LangGraph `interrupt_before` requires a checkpointer and correct resume wiring in `/chat`.

## Glossary
- **RAG**: Retrieval-Augmented Generation — retrieving relevant text chunks and injecting them into the LLM prompt so answers are grounded in a known corpus.
- **MCP**: Model Context Protocol — a standard for exposing tools/resources to an LLM agent. Here, a separate service exposes nine tools the agent discovers and calls.
- **Streamable HTTP**: the MCP transport used in production (HTTP with streamed responses), as opposed to stdio (spawned subprocess) used for local single-process dev.
- **Operational trace**: a concise, structured log of what the agent did (intent, retrieval, tool calls/results, confirmation, escalation, answer basis) — deliberately not chain-of-thought.
- **Confirmation gate**: a LangGraph interrupt that pauses before any mock action so the user must explicitly confirm.
- **Groundedness**: the degree to which every claim in an answer is supported by the retrieved context.
- **Ablation**: re-running the system with one variable changed (e.g., retrieval k) to measure its effect.
- **Northwind Robotics, Inc.**: the fictional ~650-employee robotics company whose synthetic policies and data this system serves.

## References

### Related
- [vibespec instructions](./vibespec-instructions.md)
- [vibespec structure outline](./structure.md)
- design-and-evaluation.md (rubric-facing rendering of Architecture, Data, API, Implementation, Testing, Deployment + evaluation results) — generated in Phase 8
- ai-tooling.md — describes use of vibespec + Claude Code — generated in Phase 8
- deployed.md — deployed URLs + cold-start notes — generated in Phase 6

### External
- Project brief: Quantic "AI Engineering Techniques and Architectures" project (PDF provided by the course).
- vibespec: https://github.com/joeax/vibespec
- Model Context Protocol: https://modelcontextprotocol.io
- LangGraph: https://langchain-ai.github.io/langgraph/
- Google Gemini API: https://ai.google.dev/
- sqlite-vec: https://github.com/asg017/sqlite-vec
- Railway: https://railway.app/
