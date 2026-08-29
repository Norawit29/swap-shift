"""Exact-match Thai command router — runs before the LLM."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date

from ..line import templates as T
from ..sheets.client import Ward
from ..sheets.control import active_months, month_status, read_control, set_control, set_status
from ..sheets.drift import build_diff
from ..sheets.protection import protect_tab
from ..sheets.layout import load_roster
from ..sheets.reader import validate_roster
from ..sheets.staff import read_staff
from ..shifts import load_shifts
from ..thai_date import Month, parse_month

log = logging.getLogger(__name__)

_CMD_RE = re.compile(r"^\s*(ประกาศตาราง|ตรวจตาราง|ปิดตาราง|สถานะ|ยกเลิก)\s*(.*)$")
# ขอตาราง / ตารางเวร / ลิงก์ตาราง [เดือน] → link to the month tab (anyone)
_LINK_RE = re.compile(r"^\s*(?:ขอ)?\s*(?:ลิงก์|ลิ้งก์|ลิ้ง|link)?\s*ตาราง(?:เวร)?\s*(?:เดือน)?\s*([^\s].*)?\s*(?:หน่อย|ด้วย|ค่ะ|คะ|ครับ|นะ)*\s*$")
HEAD_ONLY_CMDS = {"ประกาศตาราง", "ตรวจตาราง", "ปิดตาราง"}


@dataclass
class Command:
    name: str
    arg: str


def parse_command(text: str) -> Command | None:
    m = _CMD_RE.match(text or "")
    if m:
        return Command(m.group(1), m.group(2).strip())
    m = _LINK_RE.match(text or "")
    if m:
        arg = re.sub(r"(หน่อย|ด้วย|ค่ะ|คะ|ครับ|นะ)+$", "", (m.group(1) or "").strip()).strip()
        return Command("ตาราง", arg)
    return None


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
    try:
        loaded = load_roster(ward, m, ctl)
    except ValueError as e:
        return f"อ่านแท็บของเดือน {m.label} ไม่ได้: {e}"
    if cmd.name in ("ตรวจตาราง", "ประกาศตาราง") and loaded is None:
        return f"ไม่พบแท็บของเดือน {m.label}"
    if cmd.name == "ตรวจตาราง":
        errors = validate_roster(loaded[1], {s.staff_id for s in read_staff(ward)}, codes)
        return T.check_report(m, errors)
    if cmd.name == "ประกาศตาราง":
        if status in ("published", "live", "closed"):
            return f"ตาราง {m.label} ประกาศแล้ว (สถานะ {status})"
        title, roster = loaded
        errors = validate_roster(roster, {s.staff_id for s in read_staff(ward)}, codes)
        if errors:
            return T.check_report(m, errors) + "\nแก้ให้เรียบร้อยก่อนประกาศค่ะ"
        planned = f"{title}_planned"
        if ward.tab(planned) is None:
            src = ward.tab(title)
            ward.ss.duplicate_sheet(src.id, new_sheet_name=planned,
                                    insert_sheet_index=len(ward.ss.worksheets()))  # keep it out of the front
        protect_tab(ward, title)
        protect_tab(ward, planned)
        _hide(ward, [planned])  # tab is moved to the front only on go-live (day 1), not at publish
        # pin by sheet id: tabs get renamed and reordered, ids do not
        set_control(ward, {f"tab:{m.key}": title, f"gid:{m.key}": str(ward.tab(title).id),
                           f"planned_gid:{m.key}": str(ward.tab(planned).id)})
        set_status(ward, m, "published", by=by_display)
        return T.published(m, ward.tab_url(title))
    if cmd.name == "ปิดตาราง":
        if status not in ("published", "live"):
            return f"ตาราง {m.label} สถานะ {status or 'ไม่มี'} ปิดไม่ได้"
        n, per = build_diff(ward, m)
        set_status(ward, m, "closed", by=by_display)
        t = tab_title_for(ward, m, ctl)
        if t:
            _hide(ward, [f"{t}_diff"])
        return T.closed(m, n, [f"• {k}: {v}" for k, v in sorted(per.items(), key=lambda kv: -kv[1])])
    return "?"


def roster_link(ward: Ward, arg: str, today: date | None = None) -> str:
    """ตาราง [เดือน] → link to that month's tab (default: current active month)."""
    from ..sheets.control import current_month
    from ..sheets.layout import tab_title

    ctl = read_control(ward)
    cur = current_month(ctl, Month.from_date(today or date.today()))
    if arg in ("หน้า", "ถัดไป"):
        m, arg = cur.next(), ""
    elif arg in ("นี้", "ปัจจุบัน"):
        m, arg = cur, ""
    else:
        m = _month(arg, today) if arg else None
    if arg and m is None:
        return f"ไม่เข้าใจเดือน \"{arg}\" ค่ะ เช่น ตารางเวร ต.ค. หรือ ตารางเวร 2569-10"
    if m is None:
        m = cur
    title = tab_title(ward, m, ctl)
    if title is None:
        return f"ยังไม่มีตารางเดือน {m.label} ค่ะ"
    status = month_status(ctl, m)
    tag = {"draft": " (ร่าง — ยังไม่ประกาศ)", "": " (ยังไม่ประกาศ)", "closed": " (ปิดแล้ว)"}.get(status, "")
    return f"📅 ตารางเวร {m.label}{tag}\n{ward.tab_url(title)}"


def bring_to_front(ward: Ward, title: str, hide: list[str] | None = None) -> None:
    """Make the tab the first (leftmost) so the bare spreadsheet link opens on it; hide helper tabs."""
    try:
        ws = ward.tab(title)
        if ws is not None and ws.index != 0:
            ws.update_index(0)
        _hide(ward, hide or [])
    except Exception as e:  # noqa: BLE001
        log.warning("bring_to_front %s failed: %s", title, e)


def _hide(ward: Ward, titles: list[str]) -> None:
    for t in titles:
        ws = ward.tab(t)
        if ws is not None and not ws.isSheetHidden:
            try:
                ws.hide()
            except Exception as e:  # noqa: BLE001
                log.warning("hide %s failed: %s", t, e)


def tab_title_for(ward: Ward, m: Month, control: dict[str, str] | None = None) -> str | None:
    from ..sheets.layout import tab_title

    return tab_title(ward, m, control)


def current_display_month(ctl: dict[str, str]) -> Month | None:
    """The month users should see first: the live month, else the latest published one."""
    months = sorted(active_months(ctl))
    live = [k for k in months if ctl.get(f"status:{k}") == "live"]
    pub = [k for k in months if ctl.get(f"status:{k}") == "published"]
    key = (live or pub or [None])[-1]
    return Month.from_key(key) if key else None


def ensure_front_tab(ward: Ward, ctl: dict[str, str] | None = None) -> str | None:
    """Keep the current month's tab leftmost — that is what opening the spreadsheet link shows."""
    ctl = ctl if ctl is not None else read_control(ward)
    m = current_display_month(ctl)
    if m is None:
        return None
    t = tab_title_for(ward, m, ctl)
    if t:
        bring_to_front(ward, t)
    return t


def go_live(ward: Ward, today: date) -> list[str]:
    """Cron day 1: published → live for months whose first day ≤ today."""
    ctl = read_control(ward)
    out = []
    for key in active_months(ctl):
        m = Month.from_key(key)
        if ctl.get(f"status:{key}") == "published" and m.first_date() <= today:
            set_status(ward, m, "live")
            out.append(key)
    ensure_front_tab(ward)  # day 1: the new month takes the front; otherwise keeps the current one there
    return out
