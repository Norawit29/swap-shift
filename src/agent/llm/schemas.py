"""Pydantic schemas for OpenAI Structured Outputs (strict)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Intent = Literal["swap_report", "roster_edit", "roster_query", "confirm_reply", "command", "other"]
ShiftCode = Literal["ช", "บ", "ด", "conference", "all"]  # all = ทุกเวรของวันนั้น (ทั้งวัน)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClassifyResult(_Strict):
    intent: Intent
    confidence: float = Field(ge=0, le=1)


class SwapExtraction(_Strict):
    swap_type: Literal["exchange", "give"] | None
    a_name: str | None
    a_day: int | None
    a_month: str | None
    a_shift: ShiftCode | None
    b_name: str | None
    b_day: int | None
    b_month: str | None
    b_shift: ShiftCode | None
    missing: list[str]
    clarifying_question_th: str | None


class EditExtraction(_Strict):
    target_name: str | None
    day: int | None
    month: str | None
    new_shift: str | None  # ช/บ/ด/conference or "" for off
    missing: list[str]
    clarifying_question_th: str | None


class RosterQuery(_Strict):
    """Question about the roster: who is on a shift/day, or what shift a person has."""
    name: str | None
    day: int | None
    month: str | None
    shift: ShiftCode | None
