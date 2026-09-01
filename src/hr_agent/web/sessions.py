"""In-memory, per-process conversation sessions for ``/chat``.

Not durable and not shared across workers -- deliberate for a single-service
demo (vibespec: "session store (in-memory)"). A follow-up request carries its
``session_id``; the store hands back the prior turns as LangChain messages plus
any ``employee_id`` learned so far, so "what about abroad?" keeps its context.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

# Context is bounded to the last N messages (N / 2 completed turns).
MAX_MESSAGES = 12
# Sessions untouched for this long are dropped, swept lazily on the next access.
TTL_SECONDS = 60 * 60


@dataclass
class Session:
    history: list[BaseMessage] = field(default_factory=list)
    employee_id: str | None = None
    updated_at: float = field(default_factory=time.monotonic)


class SessionStore:
    """A dict of ``session_id -> Session`` with a lazy TTL sweep."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def get(self, session_id: str | None) -> tuple[str, Session]:
        """Return ``(session_id, session)``, creating the session if needed."""
        self._sweep()
        resolved = session_id or uuid.uuid4().hex
        return resolved, self._sessions.setdefault(resolved, Session())

    def record_turn(
        self, session_id: str, *, query: str, answer: str, employee_id: str | None = None
    ) -> None:
        """Append one completed (user, assistant) turn to the session history."""
        session = self._sessions.setdefault(session_id, Session())
        session.history.append(HumanMessage(query))
        session.history.append(AIMessage(answer or ""))
        del session.history[:-MAX_MESSAGES]
        if employee_id:
            session.employee_id = employee_id
        session.updated_at = time.monotonic()

    def _sweep(self) -> None:
        cutoff = time.monotonic() - TTL_SECONDS
        for key in [k for k, s in self._sessions.items() if s.updated_at < cutoff]:
            del self._sessions[key]
