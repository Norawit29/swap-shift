"""Thai message templates — short, phone-readable."""
from __future__ import annotations

from ..shifts import ShiftCodes
from ..thai_date import Month, fmt_day


def _line(month: Month, day: int, code: str, frm: str, to: str, codes: ShiftCodes, give: bool = False) -> str:
    return f"{fmt_day(month, day)} {codes.label(code)}: {frm} → {to}" + (" (ยกเวร)" if give else "")


def swap_lines(month: Month, a_name: str, a_day: int, a_shift: str | list[str], b_name: str,
               b_day: int | None, b_shift: str | list[str] | None, codes: ShiftCodes) -> list[str]:
    a_codes = [a_shift] if isinstance(a_shift, str) else list(a_shift)
    if b_day is None or b_shift is None:
        return [_line(month, a_day, c, a_name, b_name, codes, give=True) for c in a_codes]
    b_codes = [b_shift] if isinstance(b_shift, str) else list(b_shift)
    return ([_line(month, a_day, c, a_name, b_name, codes) for c in a_codes] +
            [_line(month, b_day, c, b_name, a_name, codes) for c in b_codes])


def edit_line(month: Month, day: int, name: str, old: str, new: str, codes: ShiftCodes) -> str:
    return f"{fmt_day(month, day)} {name}: {_cell(old, codes)} → {_cell(new, codes)}"


def _cell(v: str, codes: ShiftCodes) -> str:
    return f'"{v}"' if v else codes.off_label


def summary_swap(cid: str, lines: list[str], give: bool) -> str:
    head = f"🔄 สรุป #{cid}" if give else f"🔄 สรุปการแลกเวร #{cid}"
    return "\n".join([head, *lines, "ถูกต้องไหม?"])


def summary_edit(cid: str, line: str, warn: str | None = None) -> str:
    parts = [f"✏️ สรุปการแก้เวร #{cid}", line]
    if warn:
        parts.append(f"⚠️ {warn}")
    parts.append("ถูกต้องไหม?")
    return "\n".join(parts)


def applied(cid: str, lines: list[str]) -> str:
    return "\n".join([f"📋 อัปเดตตารางแล้ว #{cid}", *lines])


def reject(reason: str) -> str:
    return "\n".join(["❌ แจ้งไม่ตรงตาราง", reason, "ตรวจสอบแล้วแจ้งใหม่ได้เลย"])


def reject_plain(reason: str) -> str:
    return f"❌ {reason}"


def clarify(question: str, quoted: str) -> str:
    q = quoted if len(quoted) <= 60 else quoted[:57] + "…"
    return f"❓ {question}\n(จาก: {q})"


CLARIFY_GIVE_UP = "รบกวนพิมพ์ใหม่ เช่น: แลกเวรดึก 3 ต.ค. ของศรี กับ เช้า 5 ต.ค. ของบี"
ONLY_REPORTER = "เฉพาะผู้แจ้งเท่านั้น"
HEAD_ONLY = "การแก้เวรเดี่ยวทำได้เฉพาะหัวหน้าเวร"
CANCELLED = "ยกเลิกแล้ว #{cid}"
EXPIRED = "⌛ หมดเวลายืนยัน #{cid} — แจ้งใหม่ได้เลย"
NO_PENDING = "ไม่มีรายการรอยืนยัน"
CROSS_MONTH = "ยังไม่รองรับการแลกข้ามเดือน"
SHEET_CHANGED = "ตารางถูกแก้ระหว่างรอ กรุณาแจ้งใหม่"
MONTH_NOT_OPEN = "ตารางเดือนนี้ยังไม่ประกาศ / ปิดแล้ว"
MULTI_NOTE = "ℹ️ พบหลายรายการในข้อความเดียว — บันทึกรายการแรกก่อน รายการอื่นแจ้งแยกหลังยืนยันค่ะ"


def status_line(cid: str, state: str, lines: list[str]) -> str:
    th = {"PENDING_CONFIRM": "รอยืนยัน", "PENDING_CLARIFICATION": "รอข้อมูลเพิ่ม"}.get(state, state)
    return "\n".join([f"#{cid} — {th}", *lines])


def drift_alert(items: list[str]) -> str:
    return "\n".join(["⚠️ พบการแก้ตารางนอกระบบ", *items])


def published(month: Month, url: str) -> str:
    return f"📢 ประกาศตาราง {month.label} แล้ว\n{url}\nตั้งแต่นี้แก้ตารางผ่านบอทเท่านั้น"


def closed(month: Month, n_changes: int, per_person: list[str]) -> str:
    return "\n".join([f"🔒 ปิดตาราง {month.label} — เปลี่ยนแปลง {n_changes} รายการ", *per_person])


def check_report(month: Month, errors: list[str]) -> str:
    if not errors:
        return f"✅ ตาราง {month.label} ไม่พบปัญหา"
    return "\n".join([f"⚠️ ตาราง {month.label} พบ {len(errors)} ปัญหา", *errors[:20]] +
                     ([f"…และอีก {len(errors) - 20}"] if len(errors) > 20 else []))
