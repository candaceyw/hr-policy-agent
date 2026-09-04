# AI Tooling

How this project was built with AI assistance, what the human owned, and the
checks that keep AI-generated code honest.

## Tools used

| Tool | Role |
| --- | --- |
| **vibespec** ([joeax/vibespec](https://github.com/joeax/vibespec)) | Planning / scaffolding methodology. `hr-policy-agent-vibespec.md` is the *desired-state* spec; `vibespec-instructions.md` is the instruction set the agent follows for its `validate` / `plan` / `generate` commands. Not a graded deliverable. |
| **Claude Code** (Anthropic, Claude Sonnet) | The coding agent. Generated and iterated the modules and tests phase by phase, caught spec contradictions, wrote the evaluation harness, and debugged the deploy and quota issues. |
| **Gemini API** (`gemini-embedding-001`) | Corpus + query embeddings for vector retrieval. Separate free-tier quota from text generation. |
| **Groq** (`qwen/qwen3.8-27b`) | Runtime text-generation LLM for the agent loop; also `openai/gpt-oss-20b` as the evaluation judge (a different model family, so it does not grade its own output). |
| **GitHub Actions** | CI gate — lint, tests, index-determinism verify, eval smoke, SPA build. Not AI, but the discipline that AI output has to pass. |

## Workflow: spec first, then phase by phase

1. **Write the intent as a vibespec.** `hr-policy-agent-vibespec.md` describes
   *what* the system is — architecture, data entities, API, tools, acceptance
   criteria — in a desired-state form an LLM can plan against. `CLAUDE.md` holds
   the *how* (coding conventions) so the two never get mixed.
2. **Generate in phases, not one pass.** Phases 1–7: real RAG → real MCP → two
   agentic workflows → UX + sessions → two-service deploy → CI/CD → evaluation →
   docs. Phases 8–9 were eval-driven hardening passes: each targeted a specific
   metric the harness flagged (out-of-scope routing, citation precision, one
   workflow miss) and was validated by re-running the judged eval. Each phase
   ends the same way: `ruff check` clean, `pytest` green, human review of the
   diff, commit. New code ships with its tests in the same phase. Empirical work
   (retrieval quality, prompt tuning, evaluation) is iterated on real running
   code rather than guessed up front.
3. **Teach while building.** The author is taking the Quantic *AI Engineering
   Techniques and Architectures* course and needs to be able to explain the
   system. Build sessions run in a teaching style: at each design or concept
   point the agent poses a short multiple-choice question with a reference to
   where the answer lives (a file, a doc section, a URL), the author answers, and
   the agent then explains why the right option is right and the others are not.
   Decisions and non-repo lessons are logged in a private, git-ignored
   `build-note.md`.
4. **Log deviations in the spec itself.** When the implementation had to diverge
   from the plan, the reason is recorded in the vibespec's `## Issues` section —
   e.g. the MCP server moved from `mcp/server.py` to `src/hr_agent/mcp_server.py`
   because a top-level `mcp/` package shadows the installed `mcp` PyPI SDK; the
   confirmation gate is a two-call `pending_action` handshake rather than
   LangGraph `interrupt_before` + a checkpointer because `/chat` owns session
   state; `llm.py` exposes a `chat_model()` factory rather than the spec's
   hand-rolled `complete()` so LangGraph's `bind_tools` works.

## Human vs. AI

| Human (author) | AI (Claude Code) |
| --- | --- |
| Wrote the vibespec intent and the corpus facts (`corpus-facts.md`) | Generated modules, tests, and the React UI from the spec |
| Chose between options at every decision point | Surfaced the options and the trade-offs, with references |
| Reviewed every diff before commit | Wrote commit messages (AI commits are `Co-Authored-By: Claude`) |
| Ran the Railway deploys and set the dashboard config | Diagnosed the six first-deploy failures and wrote the fixes (`deployed.md`) |
| Records the demo video; shares the repo with the grader | Built the 25-item evaluation harness and wrote the analysis |

## Checks against AI error

AI output is not trusted on sight. It has to pass:

- **Tests in the same phase.** 140 tests, offline by default (an autouse fixture
  forces the no-LLM path; tool-calling tests inject a scripted model). CI runs
  the full suite plus MCP discovery + a real tool call.
- **`ruff check` clean** as a hard gate.
- **Deterministic index.** The committed vector index has a SHA-256 manifest;
  `scripts/build_index.py --verify` rebuilds and compares, in CI, on every push.
- **Green CI before deploy.** Railway's per-service *Wait for CI* holds a deploy
  until the commit's checks pass.
- **The evaluation harness is the check on answer quality** — groundedness,
  citation accuracy, tool selection, workflow completion, and action-safety are
  measured, not assumed (`evaluation/RESULTS.md`).

Concrete AI mistakes this discipline caught:

- **Evaluation judge bug.** The groundedness metric fed the judge only 220-char
  citation snippets (nothing for data-tool items), so it scored well-grounded
  answers "unsupported" (0.29). Found by reading the judge rationales; fixed by
  giving it the full gold-document text (0.73). A `--rejudge` path was added so
  the fix cost one re-score, not a full rate-limited run.
- **`--rejudge` reported a stale metric.** That same `--rejudge` path updated the
  judge scores but never recomputed each item's pass/fail flag, so `RESULTS.md`
  reported workflow completion as 6/7 when the honest figure from its own scores
  was 5/7. Caught by recomputing by hand while writing up the Tier 2 results;
  fixed by factoring the completion rule into one function called from both the
  live run and `--rejudge`, with a test.
- **A metric "improvement" that was really variance.** After the Tier 2 prompt
  changes, one workflow item (`tl-05`) dropped from 1.0 to 0.0. Before claiming a
  regression, the old prompt was re-tested on that item — it produced the same
  wrong answer — so it was logged as generator nondeterminism, not a code fault,
  and the write-up says so plainly.
- **Model choice.** An early generation model (`openai/gpt-oss-120b`) over-wrote
  and derailed on multi-tool questions; switched to `qwen/qwen3.8-27b`, which is
  tighter and reliable on tool calls.
- **Packaging.** A non-editable `pip install .` in the Docker image moved the
  package into `site-packages`, so `Path(__file__).parents[2]/"data"` resolved
  outside the container; switched to `pip install -e .`.

## Disclosures

- **Hosting.** Railway no longer offers a true free tier; this project runs on
  **Railway Hobby (paid, already owned by the author)**. Railway is named as an
  acceptable platform in the project brief. Hobby services are always-on, so
  there is no cold start to document.
- **Free-tier LLM limits shaped the evaluation.** Groq's free tier is 8000
  tokens/minute and 200k tokens/day; Gemini's judge model is 20 requests/day.
  A back-to-back 25-item judged run exceeds these, so the harness paces requests,
  retries transient failures, splits the run across days, and supports
  `--rejudge` to re-score saved answers without re-running generation. The
  authoritative 2026-09-03 run did exactly this: generation completed clean on
  Groq, the Gemini judge capped out after 8 items, and the answers were
  re-scored on the Groq judge. The tools-enabled vs RAG-only ablation ran the
  next day on a fresh budget. All documented in `evaluation/RESULTS.md` and
  `design-and-evaluation.md` §7.
- **AI-authored commits** are marked `Co-Authored-By: Claude` in the git history.
- **No model chain-of-thought is stored or exposed.** The agent trace keeps only
  operational fields (step, type, tool name, argument summary, result summary,
  sources).
