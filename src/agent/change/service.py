"""Orchestration: message → extraction → resolution → check → ChangeRequest; confirm → write."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..line import templates as T
from ..llm.client import LLM
from ..llm.schemas import EditExtraction, SwapExtraction
from ..settings import get_settings
from ..sheets.client import Ward
from ..sheets.control import active_months, current_month, month_status, read_control
from ..sheets.base import RosterBase
from ..sheets.layout import load_roster
from ..sheets.staff import read_staff
from ..sheets.writer import CellWrite, SnapshotMismatch, apply_writes
from ..shifts import load_shifts
from ..thai_date import Month, fmt_day
from .checks import CheckResult, check_edit, check_swap
from .models import ChangeRequest, utcnow
from .name_resolver import Staff, resolve
from .state_machine import can_confirm, is_expired, transition

log = logging.getLogger(__name__)


@dataclass
class Reply:
    text: str
    quick_reply_id: str | None = None  # attach [ยืนยัน][ยกเลิก] for this change id
    extra: list[str] = field(default_factory=list)


@dataclass
class Incoming:
    group_id: str
    user_id: str
    display_name: str
    text: str
    today: date | None = None


class ChangeService:
    def __init__(self, ward: Ward, llm: LLM, db: Session):
        self.ward, self.llm, self.db = ward, llm, db
        self._ctl: dict[str, str] | None = None
        self.codes = load_shifts()
        self.settings = get_settings()

    # ── context ────────────────────────────────────────────────
    def _ctx(self):
        ctl = read_control(self.ward)
        self._ctl = ctl
        staff = read_staff(self.ward)
        if not staff:  # grid layout without _staff: identity = name in cell
            today_m = Month.from_date(date.today())
            try:
                loaded = load_roster(self.ward, current_month(ctl, today_m), ctl)
            except ValueError as e:
                log.warning("staff fallback: %s", e)
                loaded = None
            if loaded:
                staff = [Staff(n, n, (n,)) for n in loaded[1].names]
        return ctl, staff

    def _roster(self, month: Month) -> RosterBase | None:
        self._roster_error = ""
        try:
            loaded = load_roster(self.ward, month, getattr(self, "_ctl", None))
        except ValueError as e:  # tab exists but cannot be parsed
            log.warning("roster parse failed for %s: %s", month.key, e)
            self._roster_error = str(e)
            return None
        if loaded is None:
            return None
        self._tab = loaded[0]
        return loaded[1]

    def _no_roster_reply(self, m: Month) -> Reply:
        err = getattr(self, "_roster_error", "")
        return Reply(T.reject_plain(f"อ่านตารางเดือน {m.label} ไม่ได้: {err}" if err else f"ไม่พบตารางเดือน {m.label}"))

    def open_request(self, user_id: str) -> ChangeRequest | None:
        q = select(ChangeRequest).where(ChangeRequest.reporter_line_id == user_id,
                                        ChangeRequest.state.in_(("PENDING_CLARIFICATION", "PENDING_CONFIRM")))
        cr = self.db.execute(q.order_by(ChangeRequest.created_at.desc())).scalars().first()
        if cr and is_expired(cr):
            transition(cr, "EXPIRED")
            self.db.flush()
            return None
        return cr

    def _cancel_open(self, user_id: str) -> None:
        for cr in self.db.execute(select(ChangeRequest).where(
                ChangeRequest.reporter_line_id == user_id,
                ChangeRequest.state.in_(("PENDING_CLARIFICATION", "PENDING_CONFIRM")))).scalars():
            transition(cr, "CANCELLED")

    # ── swap report ─────────────────────────────────────────────
    def handle_swap_report(self, msg: Incoming, prior: ChangeRequest | None = None) -> Reply:
        ctl, staff = self._ctx()
        months = active_months(ctl)
        text = f"{prior.raw_text}\n{msg.text}" if prior else msg.text
        ex = self.llm.extract_swap(text, months, msg.today)
        if prior is None:
            self._cancel_open(msg.user_id)
            cr = ChangeRequest(kind="swap", group_id=msg.group_id, month="", reporter_line_id=msg.user_id,
                               reporter_display_name=msg.display_name, raw_text=text)
            self.db.add(cr)
        else:
            cr = prior
            cr.raw_text = text
            cr.clarify_rounds += 1
        cr.llm_extraction = ex.model_dump()
        cr.touch_expiry(self.settings.change_ttl_hours)
        return self._continue_swap(cr, ex, ctl, staff, msg)

    def _continue_swap(self, cr: ChangeRequest, ex: SwapExtraction, ctl, staff: list[Staff], msg: Incoming) -> Reply:
        multi = "multiple_swaps" in ex.missing
        missing = [f for f in ex.missing if f != "multiple_swaps"]
        questions: list[str] = []
        # names
        a_res = resolve(ex.a_name or "", staff) if ex.a_name else None
        b_res = resolve(ex.b_name or "", staff) if ex.b_name else None
        for label, res, nm in (("a_name", a_res, ex.a_name), ("b_name", b_res, ex.b_name)):
            if res is None:
                if label not in missing:
                    missing.append(label)
            elif res.ambiguous:
                opts = " / ".join(s.display for s in res.matches[:4])
                questions.append(f"\"{nm}\" หมายถึงใครคะ ({opts})")
                missing.append(label)
            elif not res.ok:
                questions.append(f"ไม่พบชื่อ \"{nm}\" ในรายชื่อเจ้าหน้าที่ค่ะ ใช้ชื่อไหนคะ")
                missing.append(label)
        give = ex.swap_type == "give"
        need = ["a_day", "a_shift"] + ([] if give else ["b_day", "b_shift"])
        for f in need:
            if getattr(ex, f) is None and f not in missing:
                missing.append(f)
        if ex.swap_type is None and "swap_type" not in missing and not give:
            pass  # treat as exchange when both sides given; else b_* missing already asks
        # month
        today_m = Month.from_date(msg.today or date.today())
        default_m = current_month(ctl, today_m)
        a_m = _month_or(ex.a_month, default_m)
        b_m = _month_or(ex.b_month, default_m) if not give else a_m
        if missing or questions:
            if cr.clarify_rounds >= self.settings.max_clarify_rounds:
                transition(cr, "CANCELLED")
                return Reply(T.CLARIFY_GIVE_UP)
            q = ex.clarifying_question_th or "ช่วยระบุเพิ่มเติมค่ะ: " + ", ".join(_field_th(f) for f in missing)
            if questions:
                q = " ".join(questions) + ("" if not [m for m in missing if m in ("a_day", "a_shift", "b_day", "b_shift", "month_ambiguous")] else " " + (ex.clarifying_question_th or ""))
            if cr.state != "PENDING_CLARIFICATION":
                cr.state = "PENDING_CLARIFICATION"
            return Reply(T.clarify(q.strip(), msg.text))
        if a_m != b_m:
            transition(cr, "REJECTED")
            cr.check_result = {"ok": False, "reason": T.CROSS_MONTH}
            return Reply(T.reject_plain(T.CROSS_MONTH))
        a, b = a_res.staff, b_res.staff  # type: ignore[union-attr]
        cr.month = a_m.key
        a_sh, b_sh = _norm_shift(ex.a_shift, self.codes), _norm_shift(ex.b_shift, self.codes)
        if a_sh is None or (not give and b_sh is None):
            transition(cr, "REJECTED")
            return Reply(T.reject_plain(f"รหัสเวรไม่ถูกต้อง: {ex.a_shift if a_sh is None else ex.b_shift}"))
        cr.a_staff_id, cr.a_day, cr.a_shift = a.staff_id, ex.a_day, a_sh
        cr.b_staff_id = b.staff_id
        cr.b_day, cr.b_shift = (None, None) if give else (ex.b_day, b_sh)
        cr.swap_type = "give" if give else "exchange"
        roster = self._roster(a_m)
        if roster is None:
            transition(cr, "REJECTED")
            return self._no_roster_reply(a_m)
        res = check_swap(roster, self.codes, a, cr.a_day, _shift_arg(cr.a_shift, self.codes), b, cr.b_day,
                         _shift_arg(cr.b_shift, self.codes), month_status(ctl, a_m))
        if res.ok:  # record the concrete codes (resolves "all")
            cr.a_shift = self.codes.serialize(res.a_codes)
            if not give:
                cr.b_shift = self.codes.serialize(res.b_codes)
        reply = self._finish_check(cr, res, msg)
        if multi:
            reply.extra.append(T.MULTI_NOTE)
        return reply

    # ── roster edit ─────────────────────────────────────────────
    def handle_edit(self, msg: Incoming, prior: ChangeRequest | None = None) -> Reply:
        ctl, staff = self._ctx()
        months = active_months(ctl)
        text = f"{prior.raw_text}\n{msg.text}" if prior else msg.text
        ex = self.llm.extract_edit(text, months, msg.today)
        if prior is None:
            self._cancel_open(msg.user_id)
            cr = ChangeRequest(kind="edit", group_id=msg.group_id, month="", reporter_line_id=msg.user_id,
                               reporter_display_name=msg.display_name, raw_text=text)
            self.db.add(cr)
        else:
            cr = prior
            cr.raw_text = text
            cr.clarify_rounds += 1
        cr.llm_extraction = ex.model_dump()
        cr.touch_expiry(self.settings.change_ttl_hours)
        return self._continue_edit(cr, ex, ctl, staff, msg)

    def _continue_edit(self, cr: ChangeRequest, ex: EditExtraction, ctl, staff, msg: Incoming) -> Reply:
        missing = list(ex.missing)
        questions = []
        res = resolve(ex.target_name or "", staff) if ex.target_name else None
        if res is None:
            missing.append("target_name")
        elif res.ambiguous:
            questions.append(f"\"{ex.target_name}\" หมายถึงใครคะ ({' / '.join(s.display for s in res.matches[:4])})")
        elif not res.ok:
            questions.append(f"ไม่พบชื่อ \"{ex.target_name}\" ในรายชื่อค่ะ")
        if ex.day is None:
            missing.append("day")
        new_code = self.codes.from_text(ex.new_shift) if ex.new_shift is not None else None
        if new_code is None:
            missing.append("new_shift")
        if missing or questions:
            if cr.clarify_rounds >= self.settings.max_clarify_rounds:
                transition(cr, "CANCELLED")
                return Reply("รบกวนพิมพ์ใหม่ เช่น: เปลี่ยนพี่ศรี วันที่ 5 เป็นดึก")
            q = " ".join(questions) or ex.clarifying_question_th or "ช่วยระบุ " + ", ".join(_field_th(f) for f in missing)
            cr.state = "PENDING_CLARIFICATION"
            return Reply(T.clarify(q, msg.text))
        today_m = Month.from_date(msg.today or date.today())
        m = _month_or(ex.month, current_month(ctl, today_m))
        target = res.staff  # type: ignore[union-attr]
        cr.month, cr.target_staff_id, cr.target_day, cr.new_value = m.key, target.staff_id, ex.day, new_code
        roster = self._roster(m)
        if roster is None:
            transition(cr, "REJECTED")
            return self._no_roster_reply(m)
        check = check_edit(roster, self.codes, target, ex.day, new_code, month_status(ctl, m))  # type: ignore[arg-type]
        cr.old_value = roster.cell(target.staff_id, ex.day) if roster.has(target.staff_id) else None  # type: ignore[arg-type]
        return self._finish_check(cr, check, msg)

    # ── roster query (read-only) ───────────────────────────────
    def answer_query(self, msg: Incoming) -> Reply:
        ctl, staff = self._ctx()
        q = self.llm.extract_query(msg.text, active_months(ctl), msg.today)
        today_m = Month.from_date(msg.today or date.today())
        m = _month_or(q.month, current_month(ctl, today_m))
        roster = self._roster(m)
        if roster is None:
            return self._no_roster_reply(m)
        person = None
        if q.name:
            r = resolve(q.name, staff)
            if r.ambiguous:
                return Reply(f"\"{q.name}\" หมายถึงใครคะ ({' / '.join(s.display for s in r.matches[:4])})")
            if not r.ok:
                return Reply(f"ไม่พบชื่อ \"{q.name}\" ในตารางค่ะ")
            person = r.staff
        lab = self.codes.label
        if person and q.day:
            if not m.contains(q.day):
                return Reply(f"เดือน {m.abbr} ไม่มีวันที่ {q.day}")
            cs = self.codes.parse_cell(roster.cell(person.staff_id, q.day)) if roster.has(person.staff_id) else []
            return Reply(f"📋 {person.display} {fmt_day(m, q.day)}: " + ("+".join(lab(c) for c in cs) if cs else self.codes.off_label))
        if person:
            items = [(d, self.codes.parse_cell(v)) for (sid, d), v in sorted(roster.cells_map().items(), key=lambda kv: kv[0][1])
                     if sid == person.staff_id and v]
            if not items:
                return Reply(f"📋 {person.display} ไม่มีเวรในเดือน {m.label}")
            body = ", ".join(f"{d} {''.join(c for c in cs)}" for d, cs in items)
            return Reply(f"📋 {person.display} {m.label} ({len(items)} วัน)\n{body}")
        if q.day:
            if not m.contains(q.day):
                return Reply(f"เดือน {m.abbr} ไม่มีวันที่ {q.day}")
            by_code: dict[str, list[str]] = {}
            for (sid, d), v in roster.cells_map().items():
                if d != q.day:
                    continue
                for c in self.codes.parse_cell(v):
                    by_code.setdefault(c, []).append(roster.names.get(sid, sid))
            wanted = [q.shift] if q.shift else list(self.codes.codes)
            lines = [f"{lab(c)}: {', '.join(by_code.get(c, [])) or '-'}" for c in wanted if c in by_code or q.shift]
            return Reply(f"📋 {fmt_day(m, q.day)}\n" + ("\n".join(lines) or "ไม่มีเวร"))
        return Reply("ถามได้เช่น: ใครอยู่เวรดึก 10 ก.ย. / ธนดล วันที่ 5 เวรอะไร / ธนดลเดือนนี้เวรอะไรบ้าง")

    # ── shared ─────────────────────────────────────────────────
    def _finish_check(self, cr: ChangeRequest, res: CheckResult, msg: Incoming) -> Reply:
        cr.check_result = res.as_dict()
        if not res.ok:
            transition(cr, "REJECTED")
            return Reply(T.reject(res.reason or ""))
        cr.snapshot = {"writes": [[w.staff_id, w.day, w.row, w.col, w.before, w.after, w.code] for w in res.writes],
                       "lines": res.lines, "tab": getattr(self, "_tab", cr.month)}
        transition(cr, "PENDING_CONFIRM")
        self.db.flush()
        if cr.kind == "swap":
            text = T.summary_swap(cr.id, res.lines, give=cr.swap_type == "give")
        else:
            text = T.summary_edit(cr.id, res.lines[0], res.warning)
        return Reply(text, quick_reply_id=cr.id)

    def confirm(self, cr_id: str, user_id: str) -> Reply:
        cr = self.db.get(ChangeRequest, cr_id)
        if cr is None or cr.state != "PENDING_CONFIRM":
            return Reply(T.NO_PENDING)
        if is_expired(cr):
            transition(cr, "EXPIRED")
            return Reply(T.EXPIRED.format(cid=cr.id))
        if not can_confirm(cr, user_id):
            return Reply(T.ONLY_REPORTER)
        writes = [CellWrite(*w) for w in (cr.snapshot or {}).get("writes", [])]
        lines = (cr.snapshot or {}).get("lines", [])
        try:
            tab = (cr.snapshot or {}).get("tab", cr.month)
            apply_writes(self.ward, tab, writes, cr.id, cr.reporter_display_name, cr.kind, cr.raw_text,
                         month_key=cr.month)
        except SnapshotMismatch as e:
            log.warning("snapshot mismatch %s: %s", cr.id, e)
            transition(cr, "REJECTED")
            cr.check_result = {**(cr.check_result or {}), "ok": False, "reason": str(e)}
            return Reply(T.reject_plain(T.SHEET_CHANGED))
        transition(cr, "APPLIED")
        return Reply(T.applied(cr.id, lines) + f"\n📅 {self.ward.tab_url(tab)}")

    def cancel(self, user_id: str, cr_id: str | None = None) -> Reply:
        cr = self.db.get(ChangeRequest, cr_id) if cr_id else self.open_request(user_id)
        if cr is None or not cr.is_open:
            return Reply(T.NO_PENDING)
        if cr.reporter_line_id != user_id:
            return Reply(T.ONLY_REPORTER)
        transition(cr, "CANCELLED")
        return Reply(T.CANCELLED.format(cid=cr.id))

    def status(self, user_id: str) -> Reply:
        cr = self.open_request(user_id)
        if cr is None:
            return Reply(T.NO_PENDING)
        lines = (cr.snapshot or {}).get("lines", [])
        return Reply(T.status_line(cr.id, cr.state, lines), quick_reply_id=cr.id if cr.state == "PENDING_CONFIRM" else None)


def expire_all(db: Session) -> list[ChangeRequest]:
    out = []
    for cr in db.execute(select(ChangeRequest).where(
            ChangeRequest.state.in_(("PENDING_CLARIFICATION", "PENDING_CONFIRM")),
            ChangeRequest.expires_at <= utcnow())).scalars():
        transition(cr, "EXPIRED")
        out.append(cr)
    return out


def _norm_shift(v: str | None, codes) -> str | None:
    """LLM shift value → 'all' | serialized codes ('ช', 'บด') | None if invalid."""
    if v is None:
        return None
    lst = codes.from_words(v)
    if not lst:
        return None
    if lst == ["all"] or set(lst) >= {"ช", "บ", "ด"}:  # เช้าบ่ายดึก = ทั้งวัน
        return "all"
    order = {c: i for i, c in enumerate(codes.codes)}
    return codes.serialize(sorted(lst, key=lambda c: order.get(c, 99)))


def _shift_arg(v: str | None, codes) -> str | list[str] | None:
    if v is None or v == "all":
        return v
    lst = codes.parse_cell(v)
    return lst[0] if len(lst) == 1 else lst


def _month_or(key: str | None, default: Month) -> Month:
    if not key:
        return default
    try:
        return Month.from_key(key)
    except ValueError:
        return default


def _field_th(f: str) -> str:
    return {"a_name": "ชื่อผู้ให้", "b_name": "ชื่ออีกฝ่าย", "a_day": "วันที่ของฝ่ายแรก", "b_day": "วันที่ของอีกฝ่าย",
            "a_shift": "เวรของฝ่ายแรก", "b_shift": "เวรของอีกฝ่าย", "month_ambiguous": "เดือน",
            "target_name": "ชื่อ", "day": "วันที่", "new_shift": "เวรใหม่"}.get(f, f)
