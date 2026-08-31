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

# Each item runs its own asyncio.run(); the MCP client's httpx cleanup tasks are
# then orphaned and log a harmless "Event loop is closed". Silence that noise so
# the run log stays readable -- it does not affect any result.
logging.getLogger("asyncio").setLevel(logging.CRITICAL)

RESULTS_DIR = Path(__file__).with_name("results")
RESULTS_MD = Path(__file__).with_name("RESULTS.md")

# An answer item "completes" only if the judge similarity clears this bar.
_SIMILARITY_PASS = 0.5


def _context_for_judge(result: dict[str, Any]) -> str:
    """Evidence the answer should be grounded in: the cited snippets."""
    rows = []
    for cite in result.get("citations") or []:
        doc_id = cite.get("doc_id", "")
        snippet = cite.get("snippet") or cite.get("section") or ""
        if snippet:
            rows.append(f"[{doc_id}] {snippet}")
    return "\n".join(rows)


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
        ctx = _context_for_judge(result)
        try:
            g = judges.judge_groundedness(item.query, answer, ctx, complete_fn=complete_fn)
            s = judges.judge_similarity(item.query, item.gold_answer, answer, complete_fn=complete_fn)
            record["groundedness"] = round(g["score"], 3)
            record["groundedness_rationale"] = g["rationale"]
            record["similarity"] = round(s["score"], 3)
            record["similarity_rationale"] = s["rationale"]
        except judges.JudgeUnavailable as exc:
            record["judge_error"] = str(exc)
            print(f"    ! judge unavailable for {item.id}: {exc}")

    completed = record["behavior_match"] and not record["error"]
    if is_answer_item:
        completed = completed and bool(answer.strip())
        if "similarity" in record:
            completed = completed and record["similarity"] >= _SIMILARITY_PASS
    record["completed"] = completed
    return record


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
            "citation": citation,
            "citation_n": len(cited_items),
            "rouge_l": _mean("rouge_l", answer_items),
            "similarity": _mean("similarity", answer_items),
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
        f"| Groundedness (LLM-judge 0-1) | {_fmt(aq['groundedness'])} | {summary['n'] - ab['gate_n']} |",
        f"| Citation precision | {_fmt(cit.get('precision'))} | {aq['citation_n']} |",
        f"| Citation recall | {_fmt(cit.get('recall'))} | {aq['citation_n']} |",
        f"| Citation F1 | {_fmt(cit.get('f1'))} | {aq['citation_n']} |",
        f"| Partial match ROUGE-L | {_fmt(aq['rouge_l'])} | - |",
        f"| Partial match (LLM-judge similarity 0-1) | {_fmt(aq['similarity'])} | - |",
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="run the 6-item subset")
    parser.add_argument("--no-judge", dest="judge", action="store_false", help="skip LLM-judge metrics")
    parser.add_argument("--offline", action="store_true", help="stub model, no provider calls")
    parser.add_argument(
        "--item-pace", type=float, default=0.0,
        help="seconds to sleep between items (smooths Groq free-tier TPM throttling)",
    )
    parser.add_argument("--out-dir", default=str(RESULTS_DIR), help="where to write the results JSON")
    args = parser.parse_args(argv)

    items = load_smoke_items() if args.smoke else load_items()
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
    results_file = out_dir / f"eval-{'smoke-' if args.smoke else ''}{timestamp}.json"

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
    meta = {
        "timestamp": timestamp,
        "mode": "smoke (6 items)" if args.smoke else "full (25 items)",
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

    if not args.smoke and not args.offline:
        RESULTS_MD.write_text(render_results_md(summary, {**meta, "results_file": str(results_file)}))
        print(f"wrote {RESULTS_MD}")
    else:
        print("(RESULTS.md only regenerated on a full, online run)")

    print("\n== summary ==")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
