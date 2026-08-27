"""Grid layout — ER attending sheet: title row, day-of-week row, then week blocks
(วันที่ row + shift rows). Col B = row label, C..I = Mon..Sun, cell = staff name (optional ' TM' suffix).
Identity = name in cell (staff_id == name). Shift code derived from row label via config grid_rows."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..shifts import ShiftCodes, load_shifts, norm_label
from ..thai_date import MONTHS_FULL, Month
from .base import Move, PlanError, RosterBase
from .writer import CellWrite

_DAY_RE = re.compile(r"^\s*(\d{1,2})(?!\d)")
_TM_RE = re.compile(r"\s*TM\s*$", re.I)
_MONTH_ALIASES = {"กรกฎาคม": ("กรกฏาคม",)}
_ABBR = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
FIRST_COL, LAST_COL = 3, 9  # C..I (1-based)


def base_name(v: str) -> str:
    return _TM_RE.sub("", re.sub(r"\s+", " ", (v or "")).strip()).strip()


def _replace_name(raw: str, new: str) -> str:
    return (new + " TM") if new and _TM_RE.search(raw or "") else new


@dataclass
class Slot:
    row: int  # 1-based
    col: int
    day: int
    code: str
    raw: str

    @property
    def name(self) -> str:
        return base_name(self.raw)


@dataclass
class GridRoster(RosterBase):
    month: Month
    slots: list[Slot] = field(default_factory=list)

    @property
    def names(self) -> dict[str, str]:  # type: ignore[override]
        return {s.name: s.name for s in self.slots if s.name}

    def _slots(self, day: int, sid: str | None = None, code: str | None = None) -> list[Slot]:
        return [s for s in self.slots if s.day == day and (sid is None or s.name == sid) and (code is None or s.code == code)]

    def cell(self, sid: str, day: int) -> str:
        return load_shifts().serialize([s.code for s in self._slots(day, sid)])

    def cells_map(self) -> dict[tuple[str, int], str]:
        out: dict[tuple[str, int], list[str]] = {}
        for s in self.slots:
            if s.name:
                out.setdefault((s.name, s.day), []).append(s.code)
        codes = load_shifts()
        return {k: codes.serialize(v) for k, v in out.items()}

    def plan_moves(self, moves: list[Move]) -> list[CellWrite]:
        pending: dict[tuple[int, int], tuple[Slot, str]] = {}
        for m in moves:
            cands = [s for s in self._slots(m.day, m.from_sid, m.code) if (s.row, s.col) not in pending]
            if not cands:
                raise PlanError(f"ไม่พบ {m.from_sid} ในเวร {load_shifts().label(m.code)} วันที่ {m.day}")
            s = cands[0]
            pending[(s.row, s.col)] = (s, _replace_name(s.raw, m.to_sid))
        return [CellWrite(s.name, s.day, s.row, s.col, s.raw, after) for s, after in pending.values()
                if s.raw != after]

    def plan_set(self, sid: str, day: int, new_codes: list[str]) -> list[CellWrite]:
        codes = load_shifts()
        have = self._slots(day, sid)
        want = list(new_codes)
        writes: list[CellWrite] = []
        used: set[tuple[int, int]] = set()
        for s in have:
            if s.code in want:
                want.remove(s.code)
                used.add((s.row, s.col))
            else:
                writes.append(CellWrite(sid, day, s.row, s.col, s.raw, ""))
                used.add((s.row, s.col))
        for code in want:
            free = [s for s in self._slots(day, code=code) if not s.name and (s.row, s.col) not in used]
            if not free:
                raise PlanError(f"ไม่มีช่องว่างสำหรับเวร{codes.label(code)}วันที่ {day}")
            f = free[0]
            used.add((f.row, f.col))
            writes.append(CellWrite(sid, day, f.row, f.col, f.raw, sid))
        return writes


def parse_grid(values: list[list[str]], month: Month, codes: ShiftCodes | None = None) -> GridRoster:
    codes = codes or load_shifts()
    date_label = norm_label(codes.grid_date_label)
    slots: list[Slot] = []
    day_by_col: dict[int, int] = {}
    for r, row in enumerate(values, start=1):
        label = norm_label(row[1] if len(row) > 1 else "")
        if label == date_label:
            day_by_col = {}
            for c in range(FIRST_COL, LAST_COL + 1):
                v = row[c - 1] if len(row) >= c else ""
                m = _DAY_RE.match(str(v))
                if m and month.contains(int(m.group(1))):
                    day_by_col[c] = int(m.group(1))
            continue
        code = codes.grid_rows.get(label) if codes.grid_rows else None
        if code is None or not day_by_col:
            continue
        for c, day in day_by_col.items():
            raw = (row[c - 1] if len(row) >= c else "").strip()
            slots.append(Slot(r, c, day, code, raw))
    if not slots:
        raise ValueError("no shift rows found — check grid_rows labels in config/shifts.yaml")
    return GridRoster(month, slots)


def month_tab_title(titles: list[str], month: Month) -> str | None:
    """Rightmost tab whose name has the Thai month (+ BE/CE year) and is not a _planned/_diff tab."""
    full = MONTHS_FULL[month.month - 1]
    variants = [norm_label(v) for v in (full, *_MONTH_ALIASES.get(full, ()), _ABBR[month.month - 1])]
    years = (str(month.year_be), str(month.year_ce))
    best = best_no_year = None
    for t in titles:
        n = norm_label(t)
        if "_planned" in n or "_diff" in n or n.startswith("_"):
            continue
        if not any(v in n for v in variants):
            continue
        if any(y in n for y in years):
            best = t
        else:
            best_no_year = t
    return best or best_no_year
