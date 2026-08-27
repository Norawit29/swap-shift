"""Roster tab → typed objects. One get_all_values() per operation."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..shifts import CellParseError, ShiftCodes
from ..thai_date import Month

HEADER_FIXED = ("staff_id", "name")


@dataclass
class RosterRow:
    staff_id: str
    name: str
    row_index: int  # 1-based sheet row
    cells: dict[int, str] = field(default_factory=dict)  # day → raw cell


@dataclass
class Roster:
    month: Month
    day_cols: dict[int, int]  # day → 1-based sheet column
    rows: dict[str, RosterRow]  # staff_id → row
    header_rows: int = 1

    def cell(self, staff_id: str, day: int) -> str:
        return self.rows[staff_id].cells.get(day, "")

    def a1(self, staff_id: str, day: int) -> tuple[int, int]:
        return self.rows[staff_id].row_index, self.day_cols[day]

    def has(self, staff_id: str) -> bool:
        return staff_id in self.rows


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


def validate_roster(roster: Roster, staff_ids: set[str], codes: ShiftCodes) -> list[str]:
    """ตรวจตาราง: unknown codes, unknown staff, empty rows, missing days."""
    errors: list[str] = []
    for d in range(1, roster.month.days + 1):
        if d not in roster.day_cols:
            errors.append(f"ไม่มีคอลัมน์วันที่ {d}")
    for sid, row in roster.rows.items():
        if sid not in staff_ids:
            errors.append(f"แถว {row.row_index}: ไม่รู้จัก staff_id {sid}")
        if not any(v for v in row.cells.values()):
            errors.append(f"แถว {row.row_index} ({row.name or sid}): ว่างทั้งแถว")
        for d, v in row.cells.items():
            try:
                codes.parse_cell(v)
            except CellParseError:
                errors.append(f"{row.name or sid} วันที่ {d}: รหัสเวรไม่ถูกต้อง \"{v}\"")
    return errors
