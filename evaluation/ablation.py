"""Ablations: retrieval-k sweep and tools-enabled vs RAG-only.

    python -m evaluation.ablation                 # both ablations, full items
    python -m evaluation.ablation --ks 2 4 8

Writes ``evaluation/results/ablation-<timestamp>.json`` and prints markdown
tables for pasting into ``design-and-evaluation.md``.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evaluation import metrics
from evaluation.run_eval import RESULTS_DIR, run_item
from evaluation.schema import load_items
from hr_agent.config import settings
from hr_agent.llm import judge_available, llm_available


def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    def m(key: str) -> float | None:
        vals = [r[key] for r in records if key in r and r[key] is not None]
        return round(metrics.mean(vals), 3) if vals else None

    cited = [r["citation"] for r in records if r.get("citation")]
    citation_f1 = round(metrics.mean([c["f1"] for c in cited]), 3) if cited else None
    lat = [r["latency_s"] for r in records]
    return {
        "n": len(records),
        "groundedness": m("groundedness"),
        "similarity": m("similarity"),
        "rouge_l": m("rouge_l"),
        "citation_f1": citation_f1,
        "tool_jaccard": round(metrics.mean([r["tool_jaccard"] for r in records]), 3),
        "completion_rate": round(metrics.mean([r["completed"] for r in records]), 3),
        "latency_p50_s": metrics.percentiles(lat)["p50"],
        "latency_p95_s": metrics.percentiles(lat)["p95"],
    }


def ablate_retrieval_k(items, ks, *, judge: bool) -> dict[str, Any]:
    """RAG-only answer items at each retrieval k. Isolates k's effect on grounding."""
    targets = [it for it in items if it.expected_behavior == "answer"]
    original = settings.retrieval_k
    rows: dict[str, Any] = {}
    try:
        for k in ks:
            settings.retrieval_k = k
            print(f"\n-- retrieval_k = {k} (RAG-only, {len(targets)} items) --")
            recs = [run_item(it, judge=judge, tools=[]) for it in targets]
            rows[str(k)] = _summarize(recs)
    finally:
        settings.retrieval_k = original
    return {"variable": "retrieval_k", "values": list(ks), "results": rows}


def ablate_tools_vs_rag(items, *, judge: bool) -> dict[str, Any]:
    """The workflow items, once with MCP tools and once RAG-only."""
    targets = [it for it in items if it.is_workflow]
    print(f"\n-- tools-enabled ({len(targets)} workflow items) --")
    with_tools = [run_item(it, judge=judge) for it in targets]
    print(f"\n-- RAG-only ({len(targets)} workflow items) --")
    rag_only = [run_item(it, judge=judge, tools=[]) for it in targets]
    return {
        "variable": "tools_enabled",
        "results": {"tools_enabled": _summarize(with_tools), "rag_only": _summarize(rag_only)},
    }


def _fmt(v: Any) -> str:
    return "n/a" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))


def _print_k_table(ablation: dict[str, Any]) -> None:
    print("\n### Ablation: retrieval k (RAG-only answer items)\n")
    print("| k | groundedness | similarity | ROUGE-L | citation F1 | latency p50 (s) |")
    print("| --- | --- | --- | --- | --- | --- |")
    for k, row in ablation["results"].items():
        print(
            f"| {k} | {_fmt(row['groundedness'])} | {_fmt(row['similarity'])} | "
            f"{_fmt(row['rouge_l'])} | {_fmt(row['citation_f1'])} | {_fmt(row['latency_p50_s'])} |"
        )


def _print_tools_table(ablation: dict[str, Any]) -> None:
    print("\n### Ablation: tools-enabled vs RAG-only (workflow items)\n")
    print("| variant | completion rate | tool Jaccard | similarity | groundedness | latency p50 (s) |")
    print("| --- | --- | --- | --- | --- | --- |")
    for name, row in ablation["results"].items():
        print(
            f"| {name} | {_fmt(row['completion_rate'])} | {_fmt(row['tool_jaccard'])} | "
            f"{_fmt(row['similarity'])} | {_fmt(row['groundedness'])} | {_fmt(row['latency_p50_s'])} |"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ks", type=int, nargs="+", default=[2, 4, 8], help="retrieval k values")
    parser.add_argument("--no-judge", dest="judge", action="store_false", help="skip LLM-judge metrics")
    parser.add_argument("--only", choices=["k", "tools"], help="run just one ablation")
    parser.add_argument("--out-dir", default=str(RESULTS_DIR))
    args = parser.parse_args(argv)

    judge = args.judge and judge_available()
    if args.judge and not judge:
        print("! judge provider has no API key; running with --no-judge")
    if not llm_available():
        print("! generation provider has no API key; ablation needs the real LLM to be meaningful")

    items = load_items()
    out: dict[str, Any] = {
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ"),
        "llm_provider": settings.provider,
        "llm_model": settings.llm_model,
        "judge": judge,
        "ablations": {},
    }
    if args.only != "tools":
        out["ablations"]["retrieval_k"] = ablate_retrieval_k(items, args.ks, judge=judge)
    if args.only != "k":
        out["ablations"]["tools_vs_rag"] = ablate_tools_vs_rag(items, judge=judge)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"ablation-{out['timestamp']}.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(f"\nwrote {path}")

    if "retrieval_k" in out["ablations"]:
        _print_k_table(out["ablations"]["retrieval_k"])
    if "tools_vs_rag" in out["ablations"]:
        _print_tools_table(out["ablations"]["tools_vs_rag"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
