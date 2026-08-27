"""Exact-match Thai command router — runs before the LLM."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date

from ..line import templates as T
from ..sheets.client import Ward
from ..sheets.control import active_months, month_status, read_control, set_status
from ..sheets.drift import build_diff
from ..sheets.protection import protect_tab
from ..sheets.reader import parse_roster, validate_roster
from ..sheets.staff import read_staff
from ..shifts import load_shifts
from ..thai_date import Month, parse_month

log = logging.getLogger(__name__)

_CMD_RE = re.compile(r"^\s*(ประกาศตาราง|ตรวจตาราง|ปิดตาราง|สถานะ|ยกเลิก)\s*(.*)$")
HEAD_ONLY_CMDS = {"ประกาศตาราง", "ตรวจตาราง", "ปิดตาราง"}


@dataclass
class Command:
    name: str
    arg: str


def parse_command(text: str) -> Command | None:
    m = _CMD_RE.match(text or "")
    return Command(m.group(1), m.group(2).strip()) if m else None


def _month(arg: str, today: date | None) -> Month | None:
    return parse_month(arg, today=today) if arg else None


def run_admin(cmd: Command, ward: Ward, by_display: str, today: date | None = None) -> str:
    """ประกาศตาราง / ตรวจตาราง / ปิดตาราง — caller already checked head-nurse identity."""
    m = _month(cmd.arg, today)
    if m is None:
        return f"ระบุเดือนด้วยค่ะ เช่น {cmd.name} {Month.from_date(today or date.today()).key}"
    codes = load_shifts()
    ctl = read_control(ward)
    status = month_status(ctl, m)
    if cmd.name == "ตรวจตาราง":
        if ward.tab(m.key) is None:
            return f"ไม่พบแท็บ {m.key}"
        roster = parse_roster(ward.values(m.key), m)
        errors = validate_roster(roster, {s.staff_id for s in read_staff(ward)}, codes)
        return T.check_report(m, errors)
    if cmd.name == "ประกาศตาราง":
        if status in ("published", "live", "closed"):
            return f"ตาราง {m.label} ประกาศแล้ว (สถานะ {status})"
        if ward.tab(m.key) is None:
            return f"ไม่พบแท็บ {m.key}"
        roster = parse_roster(ward.values(m.key), m)
        errors = validate_roster(roster, {s.staff_id for s in read_staff(ward)}, codes)
        if errors:
            return T.check_report(m, errors) + "\nแก้ให้เรียบร้อยก่อนประกาศค่ะ"
        planned = f"{m.key}_planned"
        if ward.tab(planned) is None:
            src = ward.tab(m.key)
            ward.ss.duplicate_sheet(src.id, new_sheet_name=planned)
        protect_tab(ward, m.key)
        protect_tab(ward, planned)
        set_status(ward, m, "published", by=by_display)
        return T.published(m, ward.tab_url(m.key))
    if cmd.name == "ปิดตาราง":
        if status not in ("published", "live"):
            return f"ตาราง {m.label} สถานะ {status or 'ไม่มี'} ปิดไม่ได้"
        n, per = build_diff(ward, m)
        set_status(ward, m, "closed", by=by_display)
        return T.closed(m, n, [f"• {k}: {v}" for k, v in sorted(per.items(), key=lambda kv: -kv[1])])
    return "?"


def go_live(ward: Ward, today: date) -> list[str]:
    """Cron day 1: published → live for months whose first day ≤ today."""
    ctl = read_control(ward)
    out = []
    for key in active_months(ctl):
        m = Month.from_key(key)
        if ctl.get(f"status:{key}") == "published" and m.first_date() <= today:
            set_status(ward, m, "live")
            out.append(key)
    return out
