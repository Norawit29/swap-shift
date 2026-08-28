"""OpenAI Structured Outputs. Classify + extract only. Never sends LINE identifiers."""
from __future__ import annotations

import logging
from datetime import date
from functools import lru_cache
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

from ..settings import ROOT, get_settings
from ..thai_date import today_be
from .schemas import ClassifyResult, EditExtraction, RosterQuery, SwapExtraction

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)
PROMPTS = ROOT / "prompts"


@lru_cache
def _prompt(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


@lru_cache
def _client() -> OpenAI:
    s = get_settings()
    if not s.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return OpenAI(api_key=s.openai_api_key)


def _model() -> str:
    m = get_settings().openai_model
    if not m:
        raise RuntimeError("OPENAI_MODEL not set (never hardcode a model)")
    return m


def _parse(system: str, user: str, schema: type[T], *, examples: list[tuple[str, str]] | None = None) -> T:
    messages: list[dict] = [{"role": "system", "content": system}]
    for u, a in examples or []:
        messages += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
    messages.append({"role": "user", "content": user})
    resp = _client().beta.chat.completions.parse(model=_model(), messages=messages, response_format=schema)
    parsed = resp.choices[0].message.parsed
    if parsed is None:
        raise RuntimeError("LLM refused or returned no parse")
    return parsed


class LLM:
    """Thin facade so services can be given a fake in tests."""

    def classify(self, text: str) -> ClassifyResult:
        return _parse(_prompt("classify.md"), text, ClassifyResult, examples=_examples("classify"))

    def extract_swap(self, text: str, active_months: list[str], today: date | None = None) -> SwapExtraction:
        d, ybe = today_be(today)
        sys = _prompt("extract_swap.md").format(today_ce=d.isoformat(), today_be=ybe,
                                                active_months=", ".join(active_months) or "-")
        return _parse(sys, text, SwapExtraction, examples=_examples("swap"))

    def extract_edit(self, text: str, active_months: list[str], today: date | None = None) -> EditExtraction:
        d, ybe = today_be(today)
        sys = _prompt("extract_edit.md").format(today_ce=d.isoformat(), today_be=ybe,
                                                active_months=", ".join(active_months) or "-")
        return _parse(sys, text, EditExtraction, examples=_examples("edit"))


    def extract_query(self, text: str, active_months: list[str], today: date | None = None) -> RosterQuery:
        d, ybe = today_be(today)
        sys = _prompt("extract_query.md").format(today_ce=d.isoformat(), today_be=ybe,
                                                 active_months=", ".join(active_months) or "-")
        return _parse(sys, text, RosterQuery, examples=_examples("query"))


@lru_cache
def _examples(kind: str) -> list[tuple[str, str]]:
    import json

    p = PROMPTS / "extract_examples.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        ex = json.loads(line)
        if ex.get("kind") != kind:
            continue
        expected = ex["expected"]
        if kind == "classify":
            expected = {"intent": expected["intent"], "confidence": 0.95}
        out.append((ex["text"], json.dumps(expected, ensure_ascii=False)))
    return out[:40]
