"""Test doubles for the agent loop -- keeps the suite offline (no provider calls)."""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr


class ScriptedChatModel(BaseChatModel):
    """A chat model that replays a fixed list of ``AIMessage`` responses.

    ``bind_tools`` is a no-op (returns self) so the agent graph can bind the
    discovered tools without a real provider. Each ``invoke`` pops the next
    scripted response; once exhausted it returns a plain content message.
    """

    _responses: list[AIMessage] = PrivateAttr(default_factory=list)
    _calls: list[list[BaseMessage]] = PrivateAttr(default_factory=list)

    def __init__(self, responses: list[AIMessage], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._responses = list(responses)
        self._calls = []

    @property
    def calls(self) -> list[list[BaseMessage]]:
        return self._calls

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedChatModel:
        return self

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        self._calls.append(list(messages))
        if self._responses:
            message: AIMessage = self._responses.pop(0)
        else:
            message = AIMessage(content="(scripted model exhausted)")
        return ChatResult(generations=[ChatGeneration(message=message)])

    @property
    def _llm_type(self) -> str:
        return "scripted-test-model"


def tool_call(name: str, args: dict[str, Any], call_id: str) -> dict[str, Any]:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}
