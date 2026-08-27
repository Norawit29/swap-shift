"""Layout-independent roster interface used by checks / drift / commands."""
from __future__ import annotations

from dataclasses import dataclass

from ..thai_date import Month
from .writer import CellWrite


class PlanError(ValueError):
    """Write cannot be planned (e.g. no free slot) — reported to the user as a rejection."""


@dataclass(frozen=True)
class Move:
    from_sid: str
    to_sid: str
    day: int
    code: str


class RosterBase:
    month: Month
    names: dict[str, str]  # staff_id → display name in sheet

    def has(self, sid: str) -> bool:
        return sid in self.names

    def cell(self, sid: str, day: int) -> str:  # code string ('ช', 'ชบ', '')
        raise NotImplementedError

    def cells_map(self) -> dict[tuple[str, int], str]:
        raise NotImplementedError

    def plan_moves(self, moves: list[Move]) -> list[CellWrite]:
        raise NotImplementedError

    def plan_set(self, sid: str, day: int, new_codes: list[str]) -> list[CellWrite]:
        raise NotImplementedError
