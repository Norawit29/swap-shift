"""Table layout (PLAN §4): staff_id | name | 1..31, cells hold shift codes. One get_all_values() per operation."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..shifts import CellParseError, ShiftCodes, load_shifts
from ..thai_date import Month
from .base import Move, RosterBase
from .writer import CellWrite


@dataclass
class RosterRow:
    staff_id: str
    name: str
    row_index: int  # 1-based sheet row
    cells: dict[int, str] = field(default_factory=dict)  # day → raw cell


@dataclass
class Roster(RosterBase):
    month: Month
    day_cols: dict[int, int]  # day → 1-based sheet column
    rows: dict[str, RosterRow]  # staff_id → row

    @property
    def names(self) -> dict[str, str]:  # type: ignore[override]
        return {sid: r.name or sid for sid, r in self.rows.items()}

    def cell(self, staff_id: str, day: int) -> str:
        return self.rows[staff_id].cells.get(day, "")

    def cells_map(self) -> dict[tuple[str, int], str]:
        return {(sid, d): v for sid, r in self.rows.items() for d, v in r.cells.items()}

    def a1(self, staff_id: str, day: int) -> tuple[int, int]:
        return self.rows[staff_id].row_index, self.day_cols[day]

    def plan_moves(self, moves: list[Move]) -> list[CellWrite]:
        codes = load_shifts()
        new: dict[tuple[str, int], list[str]] = {}

        def cur(sid: str, d: int) -> list[str]:
            return new.setdefault((sid, d), codes.parse_cell(self.cell(sid, d)))

        for m in moves:
            cur(m.from_sid, m.day).remove(m.code)
            cur(m.to_sid, m.day).append(m.code)
        return self._writes(new, codes)

    def plan_set(self, sid: str, day: int, new_codes: list[str]) -> list[CellWrite]:
        return self._writes({(sid, day): list(new_codes)}, load_shifts())

    def _writes(self, new: dict[tuple[str, int], list[str]], codes: ShiftCodes) -> list[CellWrite]:
        out = []
        for (sid, d), lst in new.items():
            before, after = self.cell(sid, d), codes.serialize(lst)
            if before != after:
                r, c = self.a1(sid, d)
                out.append(CellWrite(sid, d, r, c, before, after))
        return out


def parse_roster(values: list[list[str]], month: Month) -> Roster:
    if not values:
        raise ValueError("empty roster tab")
    header = [h.strip() for h in values[0]]
    if len(header) < 3 or header[0].lower() != "staff_id":
        raise ValueError("roster header must start with staff_id, name, 1, 2, …")
    day_cols: dict[int, int] = {}
    for idx, h in enumerate(header[2:], start=3):
        if h.isdigit():
            d = int(h)
            if month.contains(d):
                day_cols[d] = idx
    rows: dict[str, RosterRow] = {}
    for r, row in enumerate(values[1:], start=2):
        if not row or not (row[0] or "").strip():
            continue
        sid = row[0].strip()
        name = (row[1] if len(row) > 1 else "").strip()
        cells = {d: (row[c - 1].strip() if len(row) >= c else "") for d, c in day_cols.items()}
        rows[sid] = RosterRow(sid, name, r, cells)
    return Roster(month, day_cols, rows)


def validate_roster(roster: RosterBase, staff_ids: set[str], codes: ShiftCodes) -> list[str]:
    """ตรวจตาราง: unknown codes, unknown staff, empty rows, missing days."""
    errors: list[str] = []
    if isinstance(roster, Roster):
        for d in range(1, roster.month.days + 1):
            if d not in roster.day_cols:
                errors.append(f"ไม่มีคอลัมน์วันที่ {d}")
    per_sid: dict[str, bool] = {}
    for (sid, d), v in roster.cells_map().items():
        per_sid[sid] = per_sid.get(sid, False) or bool(v)
        try:
            codes.parse_cell(v)
        except CellParseError:
            errors.append(f"{roster.names.get(sid, sid)} วันที่ {d}: รหัสเวรไม่ถูกต้อง \"{v}\"")
    for sid, any_shift in per_sid.items():
        if staff_ids and sid not in staff_ids:
            errors.append(f"ไม่รู้จัก {sid} ในรายชื่อ _staff")
        if not any_shift:
            errors.append(f"{roster.names.get(sid, sid)}: ว่างทั้งเดือน")
    return errors
