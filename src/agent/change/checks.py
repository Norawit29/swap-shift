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

    def as_dict(self) -> dict:
        return {"ok": self.ok, "reason": self.reason, "warning": self.warning,
                "writes": [(w.staff_id, w.day, w.before, w.after) for w in self.writes]}


def _cell_desc(v: str, codes: ShiftCodes) -> str:
    return f'"{v}"' if v else codes.off_label


def check_month(status: str) -> str | None:
    return None if status in WRITABLE else T.MONTH_NOT_OPEN


def check_swap(roster: RosterBase, codes: ShiftCodes, a: Staff, a_day: int, a_shift: str,
               b: Staff, b_day: int | None, b_shift: str | None, status: str) -> CheckResult:
    m: Month = roster.month
    if (r := check_month(status)):
        return CheckResult(False, r)
    if a.staff_id == b.staff_id:
        return CheckResult(False, "ผู้แลกทั้งสองเป็นคนเดียวกัน")
    give = b_day is None or b_shift is None
    # conference: exchange only, and only with another conference slot
    conf = "conference"
    if a_shift == conf or (not give and b_shift == conf):
        if give:
            return CheckResult(False, f"{codes.label(conf)} ยกให้ไม่ได้ ต้องแลกกับ {codes.label(conf)} ของอีกฝ่ายเท่านั้น")
        if a_shift != b_shift:
            return CheckResult(False, f"{codes.label(conf)} แลกได้กับ {codes.label(conf)} เท่านั้น "
                                      f"(แจ้งมา: {codes.label(a_shift)} ↔ {codes.label(b_shift)})")
    for who, d in ((a, a_day), *(() if give else ((b, b_day),))):
        if not m.contains(d):
            return CheckResult(False, f"เดือน {m.abbr} ไม่มีวันที่ {d}")
        if not roster.has(who.staff_id):
            return CheckResult(False, f"{who.display} ไม่อยู่ในตารางเดือน {m.abbr}")
    if not roster.has(b.staff_id):
        return CheckResult(False, f"{b.display} ไม่อยู่ในตารางเดือน {m.abbr}")
    try:
        a_cell = codes.parse_cell(roster.cell(a.staff_id, a_day))
        b_cell = codes.parse_cell(roster.cell(b.staff_id, b_day)) if not give else None
        a_recv = codes.parse_cell(roster.cell(a.staff_id, b_day)) if not give else None
        b_recv = codes.parse_cell(roster.cell(b.staff_id, a_day))
    except CellParseError as e:
        return CheckResult(False, f"ตารางมีรหัสเวรที่อ่านไม่ได้ ({e}) แจ้งหัวหน้าเวร")

    if a_shift not in a_cell:
        return CheckResult(False, f"{a.display} วันที่ {fmt_day(m, a_day)} ตารางระบุ "
                                  f"{_cell_desc(roster.cell(a.staff_id, a_day), codes)} ไม่ใช่ \"{a_shift}\"")
    if not give and b_shift not in b_cell:  # type: ignore[operator]
        return CheckResult(False, f"{b.display} วันที่ {fmt_day(m, b_day)} ตารางระบุ "
                                  f"{_cell_desc(roster.cell(b.staff_id, b_day), codes)} ไม่ใช่ \"{b_shift}\"")
    # after swap: receiving cell must not already hold the incoming code
    if a_shift in b_recv and not (not give and a_day == b_day and b_shift == a_shift):
        return CheckResult(False, f"{b.display} มีเวร{codes.label(a_shift)}วันที่ {fmt_day(m, a_day)} อยู่แล้ว")
    if not give and b_shift in a_recv and not (a_day == b_day and b_shift == a_shift):  # type: ignore[operator]
        return CheckResult(False, f"{a.display} มีเวร{codes.label(b_shift)}วันที่ {fmt_day(m, b_day)} อยู่แล้ว")

    moves = [Move(a.staff_id, b.staff_id, a_day, a_shift)]
    if not give:
        moves.append(Move(b.staff_id, a.staff_id, b_day, b_shift))  # type: ignore[arg-type]
    try:
        writes = roster.plan_moves(moves)
    except PlanError as e:
        return CheckResult(False, str(e))
    lines = T.swap_lines(m, a.display, a_day, a_shift, b.display, b_day, b_shift, codes)
    return CheckResult(True, writes=writes, lines=lines)


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
