"""compose_node citation selection: keep the docs the answer actually names."""

from __future__ import annotations

from hr_agent.agent.graph import _answer_names_doc, _select_citations

PTO = {"doc_id": "02-pto-and-vacation-policy", "title": "02 Pto And Vacation Policy",
       "section": "Use of PTO", "snippet": "..."}
PAYROLL = {"doc_id": "13-compensation-and-payroll", "title": "13 Compensation And Payroll",
           "section": "Overtime", "snippet": "..."}
REMOTE = {"doc_id": "04-remote-and-hybrid-work-policy", "title": "04 Remote And Hybrid Work Policy",
          "section": "Eligibility", "snippet": "..."}
OOS = {"doc_id": "05-out-of-state-and-international-remote-work", "title": "05 …",
       "section": "Key Thresholds", "snippet": "..."}


def test_answer_names_doc_matches_prose_name():
    ans = "based on the company's pto and vacation policy, you accrue 10 hours a month"
    assert _answer_names_doc("02-pto-and-vacation-policy", ans)
    assert not _answer_names_doc("13-compensation-and-payroll", ans)


def test_answer_names_doc_needs_most_significant_words():
    ans = "you may work remotely from another state with approval"  # 'remote' only, no 'hybrid'/'work policy'
    assert not _answer_names_doc("04-remote-and-hybrid-work-policy", ans)
    ans2 = "per the remote and hybrid work policy, manager approval is required"
    assert _answer_names_doc("04-remote-and-hybrid-work-policy", ans2)


def test_select_keeps_only_named_docs():
    rows = [PTO, PAYROLL]
    answer = "The PTO and Vacation Policy gives full-time staff 10 hours per month."
    kept = _select_citations(rows, answer)
    assert [r["doc_id"] for r in kept] == ["02-pto-and-vacation-policy"]


def test_select_falls_back_to_first_few_when_answer_names_none():
    rows = [PTO, PAYROLL, REMOTE, OOS, dict(PTO, section="Accrual")]
    answer = "Contact HR for the specifics of your situation."  # names no document
    kept = _select_citations(rows, answer)
    assert 1 <= len(kept) <= 4
    assert kept[0]["doc_id"] == "02-pto-and-vacation-policy"


def test_select_dedupes_and_handles_empty():
    assert _select_citations([], "anything") == []
    dupes = [PTO, dict(PTO)]
    answer = "See the PTO and Vacation Policy."
    assert len(_select_citations(dupes, answer)) == 1
