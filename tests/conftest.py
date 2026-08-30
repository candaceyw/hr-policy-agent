import sys
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# imported after SRC is on sys.path above
from _fakes import ScriptedChatModel

_OFFLINE_ANSWER = (
    "(offline test model) I can't reach a language model in this test; "
    "please contact HR for help with this request."
)


@pytest.fixture(autouse=True)
def _offline_llm(monkeypatch):
    """Keep the suite offline: no real LLM calls anywhere.

    - ``answering``/``retrieval`` are forced to their template + keyword paths.
    - The agent loop's ``chat_model`` factory is replaced with a benign
      ``ScriptedChatModel`` that answers without calling tools. Tests that need
      specific tool-calling behaviour pass their own ``model=ScriptedChatModel(...)``
      into ``run_workflow`` / ``run_agent``.
    """
    monkeypatch.setattr("hr_agent.answering.llm_available", lambda: False)
    monkeypatch.setattr("hr_agent.retrieval.embedding_available", lambda: False)
    monkeypatch.setattr(
        "hr_agent.agent.graph.chat_model",
        lambda **_: ScriptedChatModel([AIMessage(content=_OFFLINE_ANSWER)]),
    )
