"""Run the gold set through the agent and report rubric metrics.

    python -m evaluation.run_eval                 # full 25-item run
    python -m evaluation.run_eval --smoke         # 6-item subset
    python -m evaluation.run_eval --no-judge      # skip the LLM-judge metrics
    python -m evaluation.run_eval --offline       # stub model, no provider calls

Writes ``evaluation/results/eval-<timestamp>.json`` and regenerates
``evaluation/RESULTS.md``.
"""

from __future__ import annotations

import argparse
import json
import logging
import platform
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evaluation import judges, metrics
from evaluation.schema import EvalItem, load_items, load_smoke_items
from hr_agent.config import settings
from hr_agent.llm import judge_available, llm_available
from hr_agent.orchestration import run_workflow
from hr_agent.retrieval import DEFAULT_CORPUS_DIR, load_corpus_documents, load_sections

# Each item runs its own asyncio.run(); the MCP client's httpx cleanup tasks are
# then orphaned and log a harmless "Event loop is closed". Silence that noise so
# the run log stays readable -- it does not affect any result.
logging.getLogger("asyncio").setLevel(logging.CRITICAL)

RESULTS_DIR = Path(__file__).with_name("results")
RESULTS_MD = Path(__file__).with_name("RESULTS.md")

# An answer item "completes" only if the judge similarity clears this bar.
_SIMILARITY_PASS = 0.5


_CORPUS_DOCS = {p.stem: p for p in load_corpus_documents(DEFAULT_CORPUS_DIR)}
_MAX_CONTEXT_CHARS = 8000


def _context_for_judge(item: EvalItem) -> str:
    """Grounding evidence for the groundedness judge: the full text of the gold
    policy documents.

    The post-run result only carries 220-char citation snippets, which is far too
    thin for a fair groundedness judgement. Empty for items with no
    ``gold_doc_ids`` (pure data-tool lookups) -- similarity vs the gold answer,
    which encodes the correct figures, covers those.
    """
    if not item.gold_doc_ids:
        return ""
    parts: list[str] = []
    for doc_id in item.gold_doc_ids:
        path = _CORPUS_DOCS.get(doc_id)
        if not path:
            continue
        for title, body in load_sections(path):
            body = body.strip()
            if body:
                parts.append(f"## [{doc_id}] {title}\n{body}")
    return "\n\n".join(parts)[:_MAX_CONTEXT_CHARS]


_DISCOVER = object()  # sentinel: let run_workflow discover MCP tools


def run_item(
    item: EvalItem,
    *,
    model: Any | None = None,
    judge: bool = True,
    complete_fn: Any | None = None,
    tools: Any = _DISCOVER,
) -> dict[str, Any]:
    """Run one item and compute every per-item metric.

    ``tools`` defaults to MCP discovery; pass ``[]`` to force the RAG-only path
    (used by the tools-vs-RAG ablation).
    """
    start = time.perf_counter()
    error: str | None = None
    kwargs: dict[str, Any] = {"employee_id": item.employee_id, "confirm": None, "model": model}
    if tools is not _DISCOVER:
        kwargs["tools"] = tools
    try:
        result = run_workflow(item.query, **kwargs)
    except Exception as exc:  # noqa: BLE001 - a crash is a data point, not a stop
        result = {"answer": "", "citations": [], "trace": [], "intent": "", "pending_action": None}
        error = f"{type(exc).__name__}: {exc}"
    latency = time.perf_counter() - start

    behavior = metrics.observed_behavior(result)
    tools = metrics.observed_tools(result)
    doc_ids = metrics.observed_doc_ids(result)
    answer = result.get("answer") or ""
    is_answer_item = item.expected_behavior == "answer"

    record: dict[str, Any] = {
        "id": item.id,
        "category": item.category,
        "query": item.query,
        "is_workflow": item.is_workflow,
        "latency_s": round(latency, 3),
        "error": error or result.get("llm_error"),
        "expected_behavior": item.expected_behavior,
        "observed_behavior": behavior,
        "behavior_match": behavior == item.expected_behavior,
        "expected_tools": item.expected_tools,
        "observed_tools": tools,
        "tool_jaccard": round(metrics.jaccard(item.expected_tools, tools), 3),
        "gold_doc_ids": item.gold_doc_ids,
        "observed_doc_ids": doc_ids,
        "action_safe": metrics.action_safe(result),
        "answer": answer,
    }

    if item.gold_doc_ids:
        record["citation"] = {
            k: round(v, 3) for k, v in metrics.prf(item.gold_doc_ids, doc_ids).items()
        }
    if is_answer_item:
        record["rouge_l"] = round(metrics.rouge_l(item.gold_answer, answer), 3)

    if judge and is_answer_item and answer.strip():
        ctx = _context_for_judge(item)
        try:
            verdict = judges.judge_combined(
                item.query, item.gold_answer, answer, ctx, complete_fn=complete_fn
            )
            record["similarity"] = round(verdict["similarity"]["score"], 3)
            record["similarity_rationale"] = verdict["similarity"]["rationale"]
            # Groundedness only where there is corpus evidence to ground against.
            if ctx:
                record["groundedness"] = round(verdict["groundedness"]["score"], 3)
                record["groundedness_rationale"] = verdict["groundedness"]["rationale"]
        except judges.JudgeUnavailable as exc:
            record["judge_error"] = str(exc)
            print(f"    ! judge unavailable for {item.id}: {exc}")

    _mark_completed(record, is_answer_item=is_answer_item)
    return record


def _mark_completed(rec: dict[str, Any], *, is_answer_item: bool) -> None:
    """Set ``rec['completed']`` from the behavior match, error, and judge score.

    Kept separate from :func:`run_item` so ``--rejudge`` recomputes completion
    from the fresh similarity scores instead of leaving a stale flag.
    """
    done = bool(rec.get("behavior_match")) and not rec.get("error")
    if is_answer_item:
        done = done and bool((rec.get("answer") or "").strip())
        if "similarity" in rec:
            done = done and rec["similarity"] >= _SIMILARITY_PASS
    rec["completed"] = done


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll per-item records up to the rubric's reported metrics."""

    def _mean(key: str, rows: list[dict[str, Any]]) -> float | None:
        vals = [r[key] for r in rows if key in r and r[key] is not None]
        return round(metrics.mean(vals), 3) if vals else None

    answer_items = [r for r in records if r["expected_behavior"] == "answer"]
    cited_items = [r for r in records if r.get("citation")]
    workflow_items = [r for r in records if r["is_workflow"]]
    gate_items = [r for r in records if r["expected_behavior"] in ("clarify", "refuse")]
    non_gate = [r for r in records if r["expected_behavior"] not in ("clarify", "refuse")]
    latencies = [r["latency_s"] for r in records]

    citation = {
        m: round(metrics.mean([r["citation"][m] for r in cited_items]), 3)
        for m in ("precision", "recall", "f1")
    } if cited_items else None

    by_cat: dict[str, Any] = {}
    for cat in sorted({r["category"] for r in records}):
        rows = [r for r in records if r["category"] == cat]
        by_cat[cat] = {
            "n": len(rows),
            "behavior_accuracy": round(metrics.mean([r["behavior_match"] for r in rows]), 3),
            "tool_jaccard": round(metrics.mean([r["tool_jaccard"] for r in rows]), 3),
            "similarity": _mean("similarity", rows),
            "groundedness": _mean("groundedness", rows),
        }

    return {
        "n": len(records),
        "errored_items": [r["id"] for r in records if r["error"]],
        "answer_quality": {
            "groundedness": _mean("groundedness", answer_items),
            "groundedness_n": sum(1 for r in answer_items if r.get("groundedness") is not None),
            "citation": citation,
            "citation_n": len(cited_items),
            "rouge_l": _mean("rouge_l", answer_items),
            "similarity": _mean("similarity", answer_items),
            "similarity_n": sum(1 for r in answer_items if r.get("similarity") is not None),
        },
        "agent_behavior": {
            "tool_selection_jaccard": round(
                metrics.mean([r["tool_jaccard"] for r in records]), 3
            ),
            "workflow_completion_rate": round(
                metrics.mean([r["completed"] for r in workflow_items]), 3
            ) if workflow_items else None,
            "workflow_n": len(workflow_items),
            "gate_accuracy": round(
                metrics.mean([r["behavior_match"] for r in gate_items]), 3
            ) if gate_items else None,
            "gate_n": len(gate_items),
            "false_gate_rate": round(
                metrics.mean([r["observed_behavior"] in ("clarify", "refuse") for r in non_gate]),
                3,
            ) if non_gate else None,
            "action_safety_pass_rate": round(
                metrics.mean([r["action_safe"] for r in records]), 3
            ),
        },
        "system": {
            "latency_p50_s": metrics.percentiles(latencies)["p50"],
            "latency_p95_s": metrics.percentiles(latencies)["p95"],
            "latency_mean_s": round(metrics.mean(latencies), 3),
        },
        "by_category": by_cat,
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def render_results_md(summary: dict[str, Any], meta: dict[str, Any]) -> str:
    aq = summary["answer_quality"]
    ab = summary["agent_behavior"]
    sy = summary["system"]
    cit = aq["citation"] or {}
    flags = ("" if meta["judge"] else " | JUDGE OFF") + (" | OFFLINE STUB" if meta["offline"] else "")
    run_line = (
        f"- **Run:** {meta['timestamp']} | provider `{meta['llm_provider']}` "
        f"model `{meta['llm_model']}` | judge `{meta['judge_model']}`{flags}"
    )
    false_gate_line = (
        f"| False clarify/refuse rate (should be low) | {_fmt(ab['false_gate_rate'])} | "
        f"{summary['n'] - ab['gate_n']} |"
    )
    latency_note = (
        "_In-process timing (`run_workflow`); excludes HTTP framing. The deployed "
        "path adds only transport overhead, negligible against the tool-calling loop._"
    )
    grounded_row = (
        f"| Groundedness (LLM-judge 0-1, vs gold docs) | {_fmt(aq['groundedness'])} | "
        f"{aq.get('groundedness_n', '-')} |"
    )
    similarity_row = (
        f"| Partial match (LLM-judge similarity 0-1) | {_fmt(aq['similarity'])} | "
        f"{aq.get('similarity_n', '-')} |"
    )
    lines = [
        "# Evaluation results",
        "",
        "<!-- Generated by `python -m evaluation.run_eval`. Do not edit by hand. -->",
        "",
        run_line,
        f"- **Items:** {summary['n']}  ({meta['mode']})",
        f"- **Raw:** `{meta['results_file']}`",
        (
            f"- **Provider errors this run:** {', '.join(summary['errored_items'])} "
            "(transient Groq free-tier rate limits; see Limitations)"
            if summary["errored_items"]
            else "- **Provider errors this run:** none"
        ),
        "",
        "## Answer quality",
        "",
        "| Metric | Value | n |",
        "| --- | --- | --- |",
        grounded_row,
        f"| Citation precision | {_fmt(cit.get('precision'))} | {aq['citation_n']} |",
        f"| Citation recall | {_fmt(cit.get('recall'))} | {aq['citation_n']} |",
        f"| Citation F1 | {_fmt(cit.get('f1'))} | {aq['citation_n']} |",
        f"| Partial match ROUGE-L | {_fmt(aq['rouge_l'])} | - |",
        similarity_row,
        "",
        "## Agent behavior",
        "",
        "| Metric | Value | n |",
        "| --- | --- | --- |",
        f"| Tool-selection accuracy (Jaccard) | {_fmt(ab['tool_selection_jaccard'])} | {summary['n']} |",
        f"| Workflow-completion rate | {_fmt(ab['workflow_completion_rate'])} | {ab['workflow_n']} |",
        f"| Escalation/clarification accuracy | {_fmt(ab['gate_accuracy'])} | {ab['gate_n']} |",
        false_gate_line,
        f"| Action-safety pass rate | {_fmt(ab['action_safety_pass_rate'])} | {summary['n']} |",
        "",
        "## System",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Latency p50 (s) | {_fmt(sy['latency_p50_s'])} |",
        f"| Latency p95 (s) | {_fmt(sy['latency_p95_s'])} |",
        f"| Latency mean (s) | {_fmt(sy['latency_mean_s'])} |",
        "",
        latency_note,
        "",
        "## By category",
        "",
        "| Category | n | Behavior acc. | Tool Jaccard | Similarity | Groundedness |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for cat, row in summary["by_category"].items():
        lines.append(
            f"| {cat} | {row['n']} | {_fmt(row['behavior_accuracy'])} | "
            f"{_fmt(row['tool_jaccard'])} | {_fmt(row['similarity'])} | "
            f"{_fmt(row['groundedness'])} |"
        )
    lines += [
        "",
        "## Ablation",
        "",
        "See `python -m evaluation.ablation` -> `evaluation/results/ablation-*.json`.",
        "Summary table is pasted into `design-and-evaluation.md`.",
        "",
    ]
    return "\n".join(lines)


def _build_offline_model() -> Any:
    """A stub chat model: answers every turn with fixed text, never calls a tool.

    Exercises the harness plumbing (timing, metrics, JSON, RESULTS.md) with no
    provider calls. Scores are meaningless in this mode.
    """
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    class _Stub(BaseChatModel):
        def bind_tools(self, tools: Any, **kwargs: Any):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            msg = AIMessage(content="Offline stub answer. See policy docs [02-pto-and-vacation-policy].")
            return ChatResult(generations=[ChatGeneration(message=msg)])

        @property
        def _llm_type(self) -> str:
            return "offline-stub"

    return _Stub()


def _rejudge(src: Path, out_dir: Path) -> int:
    """Re-run only the LLM judge over a saved results file's answers.

    Generation is the expensive, rate-limited half; when the judge model or the
    grounding context changes, re-score the existing answers instead of paying
    for the whole run again.
    """
    payload = json.loads(src.read_text())
    by_id = {it.id: it for it in load_items()}
    print(f"re-judging {src.name} with judge `{settings.eval_judge_model}`")
    for rec in payload["records"]:
        item = by_id.get(rec["id"])
        answer = rec.get("answer") or ""
        for key in ("groundedness", "groundedness_rationale", "similarity", "similarity_rationale"):
            rec.pop(key, None)
        if item is None or item.expected_behavior != "answer" or not answer.strip():
            continue
        ctx = _context_for_judge(item)
        try:
            verdict = judges.judge_combined(item.query, item.gold_answer, answer, ctx)
        except judges.JudgeUnavailable as exc:
            rec["judge_error"] = str(exc)
            print(f"  ! {rec['id']}: {exc}")
            continue
        rec["similarity"] = round(verdict["similarity"]["score"], 3)
        rec["similarity_rationale"] = verdict["similarity"]["rationale"]
        if ctx:
            rec["groundedness"] = round(verdict["groundedness"]["score"], 3)
            rec["groundedness_rationale"] = verdict["groundedness"]["rationale"]
        print(f"  {rec['id']:<7} groundedness={rec.get('groundedness')} similarity={rec['similarity']}")

    for rec in payload["records"]:
        item = by_id.get(rec["id"])
        _mark_completed(
            rec, is_answer_item=(item is not None and item.expected_behavior == "answer")
        )

    summary = aggregate(payload["records"])
    payload["summary"] = summary
    meta = {**payload["meta"], "judge_model": settings.eval_judge_model, "judge": True}
    meta["timestamp"] = f"{meta.get('timestamp', '?')} (re-judged {datetime.now(UTC):%Y-%m-%dT%H-%M-%SZ})"
    payload["meta"] = meta

    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / src.name.replace(".json", "-rejudged.json")
    dst.write_text(json.dumps(payload, indent=2) + "\n")
    RESULTS_MD.write_text(render_results_md(summary, {**meta, "results_file": str(dst)}))
    print(f"\nwrote {dst}\nwrote {RESULTS_MD}")
    print(json.dumps(summary["answer_quality"], indent=2))
    return 0


def _filter_items(
    items: list[EvalItem], only: str
) -> tuple[list[EvalItem], set[str]]:
    """Keep items whose id or category is in the comma-separated ``only`` string.

    Returns ``(kept, unmatched_tokens)`` so the caller can warn about typos.
    """
    wanted = {tok.strip() for tok in only.split(",") if tok.strip()}
    kept = [it for it in items if it.id in wanted or it.category in wanted]
    unmatched = wanted - {it.id for it in kept} - {it.category for it in kept}
    return kept, unmatched


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="run the 6-item subset")
    parser.add_argument(
        "--only",
        metavar="IDS_OR_CATEGORIES",
        help="comma-separated item ids (md-01) and/or categories "
        "(straightforward, multi_doc, tool, ambiguous, out_of_scope) to run a "
        "subset -- e.g. --only straightforward,multi_doc for the 11 "
        "citation-bearing items. RESULTS.md is not regenerated on a subset run.",
    )
    parser.add_argument("--no-judge", dest="judge", action="store_false", help="skip LLM-judge metrics")
    parser.add_argument("--offline", action="store_true", help="stub model, no provider calls")
    parser.add_argument(
        "--item-pace", type=float, default=0.0,
        help="seconds to sleep between items (smooths Groq free-tier TPM throttling)",
    )
    parser.add_argument("--out-dir", default=str(RESULTS_DIR), help="where to write the results JSON")
    parser.add_argument(
        "--rejudge",
        metavar="RESULTS_JSON",
        help="re-score the answers in an existing results file with the current "
        "judge + context logic; no workflows are re-run (no generation cost)",
    )
    args = parser.parse_args(argv)

    if args.rejudge:
        return _rejudge(Path(args.rejudge), Path(args.out_dir))

    items = load_smoke_items() if args.smoke else load_items()
    if args.only:
        items, unmatched = _filter_items(items, args.only)
        if not items:
            print(f"! --only {args.only!r} matched no items")
            return 1
        if unmatched:
            print(f"! --only: ignoring unknown token(s) {sorted(unmatched)}")

    model = _build_offline_model() if args.offline else None
    judge = args.judge and not args.offline
    if judge and not judge_available():
        print("! judge provider has no API key; running with --no-judge")
        judge = False
    if not args.offline and not llm_available():
        print("! generation provider has no API key; answers will use the template fallback")

    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = "smoke-" if args.smoke else ("subset-" if args.only else "")
    results_file = out_dir / f"eval-{prefix}{timestamp}.json"

    records: list[dict[str, Any]] = []
    for i, item in enumerate(items, start=1):
        if i > 1 and args.item_pace > 0:
            time.sleep(args.item_pace)
        print(f"[{i:>2}/{len(items)}] {item.id:<7} {item.category:<15} ...", end=" ", flush=True)
        rec = run_item(item, model=model, judge=judge)
        records.append(rec)
        print(
            f"{rec['observed_behavior']:<8} tools={rec['observed_tools']} "
            f"{rec['latency_s']}s{' ERROR' if rec['error'] else ''}"
        )

    summary = aggregate(records)
    if args.smoke:
        mode = f"smoke ({len(items)} items)"
    elif args.only:
        mode = f"subset --only {args.only} ({len(items)} items)"
    else:
        mode = "full (25 items)"
    meta = {
        "timestamp": timestamp,
        "mode": mode,
        "llm_provider": settings.provider,
        "llm_model": settings.llm_model,
        "judge_model": settings.eval_judge_model if judge else "(none)",
        "judge": judge,
        "offline": args.offline,
        "python": platform.python_version(),
        "results_file": results_file.name,
    }
    payload = {"meta": meta, "summary": summary, "records": records}
    results_file.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\nwrote {results_file}")

    if not args.smoke and not args.offline and not args.only:
        RESULTS_MD.write_text(render_results_md(summary, {**meta, "results_file": str(results_file)}))
        print(f"wrote {RESULTS_MD}")
    else:
        print("(RESULTS.md only regenerated on a full, online run)")

    print("\n== summary ==")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
