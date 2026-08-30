# AGENTS.md — coding conventions for hr-policy-agent

This file holds coding conventions and agent guidance. System design lives in
`hr-policy-agent-vibespec.md` (the vibespec). Keep the two separate: the vibespec
describes *what* the system is; this file describes *how* we write the code.

## Workflow
- This project is generated with vibespec (https://github.com/joeax/vibespec).
- `vibespec-instructions.md` is the loaded instruction set. Commands: `validate`,
  `plan`, `setup`, `generate` / `update`, `describe`.
- Build **phase by phase** (Phase 0-8 in the vibespec's Setup / build notes).
  After each phase: run `ruff` + `pytest`, review, commit, then continue.
- The `.vibespec/` folder holds the execution plan and codebase summary — commit it
  alongside code changes for an audit trail.

## Language & tooling
- Python 3.12, pinned via `.python-version`.
- `uv` for env and dependency management. `uv add` to add deps; commit `uv.lock`.
- `ruff` for lint and format (default rules; line length 100). `ruff check` must be clean.
- `pytest` (+ `pytest-asyncio`) for tests. New code ships with tests in the same phase.
- Type hints on all public functions. `pydantic` v2 for all external/tool schemas.

## Conventions
- Module layout follows the Folder Structure section of the vibespec exactly.
- The only file that imports `google-genai` is `src/hr_agent/llm.py`. Everything else
  calls that wrapper, so the provider can be swapped via config.
- All configuration comes from `src/hr_agent/config.py` (env-backed Pydantic Settings).
  No hard-coded model names, ports, k values, chunk sizes, or URLs anywhere else.
- Secrets only from environment variables. Never commit `.env`. Keep `.env.example`
  in sync with every variable the code reads.
- Determinism: chunking must be pure and reproducible; anything that samples uses
  `SEED` from config via `seeds.py`.
- MCP tools return typed results or `{"error": "<code>", "message": "..."}` — never
  raise across the MCP boundary.
- The agent trace stores only operational fields (step, type, name, args_summary,
  result_summary, sources). Never store or expose model chain-of-thought.
- Mock actions (`create_mock_hr_ticket`, `draft_hr_email`) never touch committed data
  and are always reached through the confirmation gate.

## Testing rules
- Every phase that adds code adds or updates tests in `tests/`.
- Tests must not require network except where they explicitly exercise the Gemini
  API; those are marked and kept minimal. Prefer fixtures and a tiny sample corpus.
- CI runs lint, the full unit + integration suite, the index determinism check, and
  a reduced evaluation smoke subset. Deploy only if all pass.

## Git
- Do not commit or push unless asked.
- Branch off `main` for changes; `main` is protected and deploys only on green CI.
- Commit the vibespec and the code it generated together.
