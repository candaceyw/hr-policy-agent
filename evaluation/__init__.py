"""Evaluation harness: gold set, metrics, LLM judge, runner, and ablations.

Not imported by the application. Run as scripts:

    python -m evaluation.run_eval        # full 25-item run -> results/ + RESULTS.md
    python -m evaluation.run_eval --smoke # 6-item offline subset (CI)
    python -m evaluation.ablation         # retrieval-k and tools-vs-RAG sweeps
"""
