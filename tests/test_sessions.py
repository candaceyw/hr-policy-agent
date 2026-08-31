"""Unit tests for the in-memory conversation session store."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from hr_agent.web import sessions
from hr_agent.web.sessions import MAX_MESSAGES, SessionStore


def test_get_creates_and_reuses_a_session():
    store = SessionStore()
    sid, session = store.get(None)
    assert sid and session.history == []

    same_id, same_session = store.get(sid)
    assert same_id == sid
    assert same_session is session


def test_record_turn_appends_user_then_assistant_messages():
    store = SessionStore()
    sid, _ = store.get(None)
    store.record_turn(sid, query="How much PTO do I have?", answer="You have 68 hours.")

    _, session = store.get(sid)
    assert [type(m) for m in session.history] == [HumanMessage, AIMessage]
    assert session.history[0].content == "How much PTO do I have?"
    assert session.history[1].content == "You have 68 hours."


def test_history_is_capped_at_max_messages():
    store = SessionStore()
    sid, _ = store.get(None)
    for i in range(MAX_MESSAGES):  # 2 messages per turn -> MAX_MESSAGES turns overfills
        store.record_turn(sid, query=f"q{i}", answer=f"a{i}")

    _, session = store.get(sid)
    assert len(session.history) == MAX_MESSAGES
    # oldest turns dropped; the most recent one survives
    assert session.history[-2].content == f"q{MAX_MESSAGES - 1}"


def test_learned_employee_id_sticks():
    store = SessionStore()
    sid, _ = store.get(None)
    store.record_turn(sid, query="hi", answer="hello", employee_id="E-1002")
    store.record_turn(sid, query="and now?", answer="ok")  # no id this turn

    _, session = store.get(sid)
    assert session.employee_id == "E-1002"


def test_stale_sessions_are_swept(monkeypatch):
    store = SessionStore()
    sid, _ = store.get(None)
    store.record_turn(sid, query="q", answer="a")

    monkeypatch.setattr(sessions, "TTL_SECONDS", -1)  # everything is stale
    _, session = store.get(sid)
    assert session.history == []  # old session was swept, a fresh one returned
