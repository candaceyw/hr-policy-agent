"""Gold-set item schema and JSONL loader."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["straightforward", "multi_doc", "tool", "ambiguous", "out_of_scope"]
Behavior = Literal["answer", "clarify", "refuse", "confirm"]

QUESTIONS_PATH = Path(__file__).with_name("eval_questions.jsonl")

# The 6 items the CI smoke subset runs (one per behavior, plus a multi-doc and a
# tool item). Kept small so the offline CI run stays fast and token-free.
SMOKE_IDS = ("sq-01", "md-05", "tl-01", "tl-06", "am-01", "oos-01")


class EvalItem(BaseModel):
    """One gold evaluation item."""

    id: str
    category: Category
    query: str
    employee_id: str | None = None
    gold_doc_ids: list[str] = Field(default_factory=list)
    gold_answer: str
    expected_tools: list[str] = Field(default_factory=list)
    expected_behavior: Behavior
    is_workflow: bool = False


def load_items(path: str | Path | None = None) -> list[EvalItem]:
    """Load and validate every item from the JSONL gold set."""
    path = Path(path) if path else QUESTIONS_PATH
    items: list[EvalItem] = []
    for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            items.append(EvalItem.model_validate_json(raw))
        except Exception as exc:
            raise ValueError(f"{path.name}:{lineno}: {exc}") from exc
    return items


def load_smoke_items(path: str | Path | None = None) -> list[EvalItem]:
    """The reduced subset used by CI."""
    by_id = {item.id: item for item in load_items(path)}
    return [by_id[i] for i in SMOKE_IDS if i in by_id]
