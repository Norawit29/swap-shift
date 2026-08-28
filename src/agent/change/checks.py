"""Consistency check — deterministic, PLAN §7. Produces rejection text with the real roster value."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..line import templates as T
from ..sheets.control import WRITABLE
from ..sheets.base import Move, PlanError, RosterBase
from ..sheets.writer import CellWrite
from ..shifts import CellParseError, ShiftCodes
from ..thai_date import Month, fmt_day
from .name_resolver import Staff


@dataclass
class CheckResult:
    ok: bool
    reason: str | None = None
    warning: str | None = None
    writes: list[CellWrite] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    a_codes: list[str] = field(default_factory=list)  # resolved codes A gives (after expanding "all")
    b_codes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"ok": self.ok, "reason": self.reason, "warning": self.warning,
                "writes": [(w.staff_id, w.day, w.before, w.after) for w in self.writes]}


def _cell_desc(v: str, codes: ShiftCodes) -> str:
    return f'"{v}"' if v else codes.off_label


def check_month(status: str) -> str | None:
    return None if status in WRITABLE else T.MONTH_NOT_OPEN


def check_swap(roster: RosterBase, codes: ShiftCodes, a: Staff, a_day: int, a_shift: str | list[str],
               b: Staff, b_day: int | None, b_shift: str | list[str] | None, status: str) -> CheckResult:
    """a_shift / b_shift: a code, a list of codes, or "all" (= every code that person holds on that day)."""
    m: Month = roster.month
    if (r := check_month(status)):
        return CheckResult(False, r)
    if a.staff_id == b.staff_id:
        return CheckResult(False, "ผู้แลกทั้งสองเป็นคนเดียวกัน")
    give = b_day is None or b_shift is None
    for who, d in ((a, a_day), *(() if give else ((b, b_day),))):
        if not m.contains(d):
            return CheckResult(False, f"เดือน {m.abbr} ไม่มีวันที่ {d}")
        if not roster.has(who.staff_id):
            return CheckResult(False, f"{who.display} ไม่อยู่ในตารางเดือน {m.abbr}")
    if not roster.has(b.staff_id):
        return CheckResult(False, f"{b.display} ไม่อยู่ในตารางเดือน {m.abbr}")
    try:
        a_cell = codes.parse_cell(roster.cell(a.staff_id, a_day))
        b_cell = codes.parse_cell(roster.cell(b.staff_id, b_day)) if not give else []
        a_recv = codes.parse_cell(roster.cell(a.staff_id, b_day)) if not give else []
        b_recv = codes.parse_cell(roster.cell(b.staff_id, a_day))
    except CellParseError as e:
        return CheckResult(False, f"ตารางมีรหัสเวรที่อ่านไม่ได้ ({e}) แจ้งหัวหน้าเวร")

    a_codes = _expand(a_shift, a_cell)
    b_codes = _expand(b_shift, b_cell) if not give else []
    if not a_codes:
        return CheckResult(False, f"{a.display} วันที่ {fmt_day(m, a_day)} ตารางระบุ {codes.off_label} — ไม่มีเวรให้แลก")
    if not give and not b_codes:
        return CheckResult(False, f"{b.display} วันที่ {fmt_day(m, b_day)} ตารางระบุ {codes.off_label} — ไม่มีเวรให้แลก")

    # conference: exchange only, and only against conference on the other side
    conf = "conference"
    if conf in a_codes or conf in b_codes:
        if give:
            return CheckResult(False, f"{codes.label(conf)} ยกให้ไม่ได้ ต้องแลกกับ {codes.label(conf)} ของอีกฝ่ายเท่านั้น")
        if (conf in a_codes) != (conf in b_codes):
            return CheckResult(False, f"{codes.label(conf)} แลกได้กับ {codes.label(conf)} เท่านั้น "
                                      f"(แจ้งมา: {_labels(a_codes, codes)} ↔ {_labels(b_codes, codes)})")

    for c in a_codes:
        if c not in a_cell:
            return CheckResult(False, f"{a.display} วันที่ {fmt_day(m, a_day)} ตารางระบุ "
                                      f"{_cell_desc(roster.cell(a.staff_id, a_day), codes)} ไม่ใช่ \"{c}\"")
    for c in b_codes:
        if c not in b_cell:
            return CheckResult(False, f"{b.display} วันที่ {fmt_day(m, b_day)} ตารางระบุ "
                                      f"{_cell_desc(roster.cell(b.staff_id, b_day), codes)} ไม่ใช่ \"{c}\"")
    same_day = (not give) and a_day == b_day
    for c in a_codes:  # B receives c on a_day
        already = c in b_recv and not (same_day and c in b_codes)
        if already:
            return CheckResult(False, f"{b.display} มีเวร{codes.label(c)}วันที่ {fmt_day(m, a_day)} อยู่แล้ว")
    for c in b_codes:  # A receives c on b_day
        already = c in a_recv and not (same_day and c in a_codes)
        if already:
            return CheckResult(False, f"{a.display} มีเวร{codes.label(c)}วันที่ {fmt_day(m, b_day)} อยู่แล้ว")

    moves = [Move(a.staff_id, b.staff_id, a_day, c) for c in a_codes]
    moves += [Move(b.staff_id, a.staff_id, b_day, c) for c in b_codes]  # type: ignore[arg-type]
    try:
        writes = roster.plan_moves(moves)
    except PlanError as e:
        return CheckResult(False, str(e))
    lines = T.swap_lines(m, a.display, a_day, a_codes, b.display, b_day, b_codes or None, codes)
    return CheckResult(True, writes=writes, lines=lines, a_codes=a_codes, b_codes=b_codes)


def _expand(shift: str | list[str] | None, cell_codes: list[str]) -> list[str]:
    if shift is None:
        return []
    if shift == "all":
        return list(cell_codes)
    return list(shift) if isinstance(shift, list) else [shift]


def _labels(cs: list[str], codes: ShiftCodes) -> str:
    return "+".join(codes.label(c) for c in cs) or codes.off_label


def check_edit(roster: RosterBase, codes: ShiftCodes, target: Staff, day: int, new_value: str,
               status: str, implied_old: str | None = None) -> CheckResult:
    m = roster.month
    if (r := check_month(status)):
        return CheckResult(False, r)
    if not m.contains(day):
        return CheckResult(False, f"เดือน {m.abbr} ไม่มีวันที่ {day}")
    if not roster.has(target.staff_id):
        return CheckResult(False, f"{target.display} ไม่อยู่ในตารางเดือน {m.abbr}")
    try:
        new_codes = codes.parse_cell(new_value)
    except CellParseError:
        return CheckResult(False, f"รหัสเวร \"{new_value}\" ไม่ถูกต้อง")
    before = roster.cell(target.staff_id, day)
    warn = None
    if implied_old is not None and implied_old != before:
        warn = f"ตารางปัจจุบันระบุ {_cell_desc(before, codes)} ไม่ใช่ {_cell_desc(implied_old, codes)}"
    if before == new_value:
        return CheckResult(False, f"{target.display} วันที่ {fmt_day(m, day)} เป็น {_cell_desc(before, codes)} อยู่แล้ว")
    try:
        writes = roster.plan_set(target.staff_id, day, new_codes)
    except PlanError as e:
        return CheckResult(False, str(e))
    return CheckResult(True, warning=warn, writes=writes,
                       lines=[T.edit_line(m, day, target.display, before, new_value, codes)])
