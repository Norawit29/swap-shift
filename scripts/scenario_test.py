"""Exploratory scenario run against the REAL LLM + REAL sheet, with LINE sends captured (nothing posted to the group).
DRY_RUN=true so roster cells are not modified (except the explicit drift/snapshot cases, which are reverted).
usage: DRY_RUN=true DATABASE_URL=sqlite:///./scenario.db python scripts/scenario_test.py
"""
from __future__ import annotations

import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

os.environ.setdefault("DRY_RUN", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///./scenario.db")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent import main as M  # noqa: E402
from agent.change.models import ChangeRequest, utcnow  # noqa: E402
from agent.db import init_db, session  # noqa: E402
from agent.llm.client import LLM  # noqa: E402
from agent.settings import get_settings  # noqa: E402
from agent.sheets.client import Ward  # noqa: E402
from agent.sheets.drift import detect_drift  # noqa: E402
from agent.thai_date import Month  # noqa: E402

S = get_settings()
GROUP = next(iter(S.allowed_groups))
HEAD = next(iter(S.head_nurse_ids))
NURSE = "U_test_nurse_0000000000000000000"
TODAY = date(2026, 9, 1)  # pretend we're inside the published month
llm = LLM()


class FakeLine:
    def __init__(self):
        self.out: list[tuple[list[str], str | None]] = []

    def send(self, token, group_id, texts, quick_reply_id=None, image_url=None):
        self.out.append((texts, quick_reply_id))

    def push(self, to, texts, quick_reply_id=None, image_url=None):
        self.out.append((texts, quick_reply_id))

    def display_name(self, g, u):
        return "หัวหน้า" if u == HEAD else "พยาบาลทดสอบ"


def msg(text, user=HEAD):
    return {"type": "message", "replyToken": "x", "source": {"type": "group", "groupId": GROUP, "userId": user},
            "message": {"type": "text", "text": text}}


def postback(data, user=HEAD):
    return {"type": "postback", "replyToken": "x", "source": {"type": "group", "groupId": GROUP, "userId": user},
            "postback": {"data": data}}


results: list[tuple[str, str, str]] = []


START = os.environ.get("FROM", "")
_started = [not START]


def run(case: str, ev: dict, expect: str = "") -> tuple[list[str], str | None]:
    if not _started[0]:
        if case.startswith(START):
            _started[0] = True
        else:
            return [], None
    time.sleep(float(os.environ.get("PAUSE", "0")))
    line = FakeLine()
    t0 = time.time()
    M._handle(ev, line, llm, TODAY)
    dt = time.time() - t0
    texts = [t for ts, _ in line.out for t in ts]
    qr = next((q for _, q in line.out if q), None)
    reply = " | ".join(t.replace("\n", " / ") for t in texts) or "(silent)"
    results.append((case, f"{dt:.1f}s", reply + (f"  [buttons #{qr}]" if qr else "")))
    print(f"\n### {case}\n  expect: {expect}\n  got   : {reply}{'  [buttons #' + qr + ']' if qr else ''}  ({dt:.1f}s)")
    return texts, qr


def last_id(user=HEAD):
    with session() as db:
        from sqlalchemy import select
        cr = db.execute(select(ChangeRequest).order_by(ChangeRequest.created_at.desc())).scalars().first()
        return cr.id if cr else None


def main():
    if not START:
        Path("scenario.db").unlink(missing_ok=True)
    init_db()
    # ── A. reports ──
    _, q = run("A1 exchange single (standard)", msg("แลกเวรดึก 10 ก.ย. ของธนวัฒน์ กับ เช้า 3 ก.ย. ของธนดล"), "summary + buttons")
    if q:
        run("A1b confirm by OTHER user", postback(f"action=confirm&id={q}", NURSE), "เฉพาะผู้แจ้งเท่านั้น")
        run("A1c confirm by reporter", postback(f"action=confirm&id={q}"), "อัปเดตตารางแล้ว + link (dry-run)")
        run("A1d confirm again (double tap)", postback(f"action=confirm&id={q}"), "ไม่มีรายการรอยืนยัน")
    run("A2 whole day", msg("อรรถสิทธิ์แลกวันที่ 3 กับคมสันติวันที่ 7"), "summary 6 lines")
    run("A2b cancel via text", msg("ยกเลิก"), "ยกเลิกแล้ว")
    run("A3 give (ยกเวร)", msg("ภัทรพลยกเวรดึก 4 ก.ย. ให้ธนดล"), "summary (ยกเวร) + buttons")
    run("A3b ok ค่ะ free-text confirm", msg("ok ค่ะ"), "อัปเดตตารางแล้ว")
    run("A4 prefix พี่/น้อง", msg("พี่ธนดลแลกเวรเช้า 18 ก.ย. กับ น้องขวัญศิริ เช้า 19 ก.ย."), "summary + buttons")
    run("A4b new report auto-cancels previous", msg("ปวีณอรแลกเวรเช้า 5 ก.ย. กับ ธนดล เช้า 6 ก.ย."), "summary; previous pending cancelled")
    run("A4c สถานะ", msg("สถานะ"), "shows latest pending only")
    run("A4d ยกเลิก", msg("ยกเลิก"), "ยกเลิกแล้ว")
    run("A5 ambiguous name (ธน = ธนดล/ธนวัฒน์)", msg("แลกเวรเช้า 3 ก.ย. ของธน กับ เช้า 18 ก.ย. ของขวัญศิริ"), "ask which person")
    run("A5b answer clarification", msg("ธนดล"), "summary + buttons")
    run("A5c ยกเลิก", msg("ยกเลิก"), "")
    run("A6 unknown name", msg("แลกเวรเช้า 3 ก.ย. ของสมชาย กับ เช้า 18 ก.ย. ของขวัญศิริ"), "ไม่พบชื่อ → ask")
    run("A6b give up round 2", msg("สมชายครับ"), "ask again or give-up template")
    run("A6c give up round 3", msg("สมชาย"), "รบกวนพิมพ์ใหม่ (cancelled)")
    run("A7 missing date", msg("ธนดลแลกเวรเช้ากับขวัญศิริ"), "ask date")
    run("A7b answer dates", msg("ธนดล 18 ขวัญศิริ 19"), "summary")
    run("A7c ยกเลิก", msg("ยกเลิก"), "")
    run("A8 relative date พรุ่งนี้ (today=1 ก.ย.)", msg("แลกเวรเช้าพรุ่งนี้ของภควดี กับ เช้า 3 ก.ย. ของธนดล"), "2 ก.ย. resolved → summary or reject")
    run("A8b ยกเลิก", msg("ยกเลิก"), "")
    run("A9 cross-month", msg("แลกเวรเช้า 30 ก.ย. ของปวีณอร กับ เช้า 2 ต.ค. ของธนดล"), "ยังไม่รองรับข้ามเดือน")
    run("A10 same person", msg("แลกเวรเช้า 3 ก.ย. ของธนดล กับ บ่าย 18 ก.ย. ของธนดล"), "คนเดียวกัน")
    run("A11 not on shift", msg("แลกเวรดึก 3 ก.ย. ของธนดล กับ เช้า 18 ก.ย. ของขวัญศิริ"), "ตารางระบุ ช ไม่ใช่ ด")
    run("A12 receiver already has code", msg("ครองวงศ์ยกเวรเช้า 2 ก.ย. ให้นรวิชญ์"), "นรวิชญ์ มีเวรเช้าวันที่ 2 อยู่แล้ว")
    run("A13 conference ↔ เช้า", msg("แลก conference 2 ก.ย. ของวรวรรธน์ กับ เช้า 3 ก.ย. ของธนดล"), "conference เท่านั้น")
    run("A14 English mixed", msg("swap night 10 Sep ธนวัฒน์ with morning 3 Sep ธนดล"), "summary")
    run("A14b ยกเลิก", msg("ยกเลิก"), "")
    run("A15 date 10/9 + กย no dot", msg("แลกเวรดึก 10/9 ของธนวัฒน์ กับ เช้า 3 กย ของธนดล"), "summary")
    run("A15b ยกเลิก", msg("ยกเลิก"), "")
    run("A16 two swaps in one message", msg("แลกเวรเช้า 3 ก.ย. ธนดล↔ขวัญศิริ 18 ก.ย. และ ดึก 10 ก.ย. ธนวัฒน์↔ธนดล 3 ก.ย."), "?? only one handled")
    run("A16b ยกเลิก", msg("ยกเลิก"), "")
    run("A17 off day whole", msg("ธนดลแลกวันที่ 12 กับคมสันติวันที่ 7"), "ไม่มีเวรให้แลก")
    run("A18 typo แลกเวอร์", msg("แลกเวอร์เช้า 3 กย ธนดล กับ ขวัญศิริ 18 กย เช้า"), "summary")
    run("A18b ยกเลิก", msg("ยกเลิก"), "")
    run("A19 buddhist year full", msg("แลกเวรเช้า 3/9/2569 ของธนดล กับ เช้า 18/9/2569 ของขวัญศิริ"), "summary")
    run("A19b ยกเลิก", msg("ยกเลิก"), "")
    # ── B. head-only edits ──
    run("B1 edit by nurse", msg("เปลี่ยนธนดล วันที่ 12 เป็นดึก", NURSE), "เฉพาะหัวหน้าเวร")
    run("B2 edit to free slot", msg("เปลี่ยนธนดล วันที่ 12 เป็นดึก"), "summary + buttons")
    run("B2b ยกเลิก", msg("ยกเลิก"), "")
    run("B3 edit to full slot", msg("เปลี่ยนธนดล วันที่ 10 เป็นเช้า"), "ไม่มีช่องว่าง")
    run("B4 edit to off", msg("ธนดล วันที่ 3 หยุด"), "summary → หยุด")
    run("B4b ยกเลิก", msg("ยกเลิก"), "")
    run("B5 edit unchanged", msg("เปลี่ยนธนดล วันที่ 3 เป็นเช้า"), "เป็น ช อยู่แล้ว")
    # ── C. commands ──
    run("C1 ตรวจตาราง by nurse", msg("ตรวจตาราง 2569-09", NURSE), "เฉพาะหัวหน้า")
    run("C2 ประกาศ again", msg("ประกาศตาราง 2569-09"), "ประกาศแล้ว (published)")
    run("C3 ตาราง เดือนหน้า", msg("ตารางเวรเดือนหน้า"), "ยังไม่มีตารางเดือน ตุลาคม")
    run("C4 ตาราง ส.ค. (unpublished old)", msg("ขอตารางเวร ส.ค."), "link (ร่าง)")
    run("C5 สถานะ none", msg("สถานะ", NURSE), "ไม่มีรายการ")
    run("C6 ตรวจตาราง ต.ค. missing", msg("ตรวจตาราง ต.ค."), "ไม่พบแท็บ")
    # ── D. noise ──
    run("D1 chit-chat", msg("วันนี้ฝนตกหนักมาก"), "(silent)")
    run("D2 roster question", msg("ใครอยู่เวรดึก 10 ก.ย. บ้าง"), "(silent) — gap?")
    run("D3 sticker", {"type": "message", "replyToken": "x", "source": {"type": "group", "groupId": GROUP, "userId": HEAD}, "message": {"type": "sticker"}}, "(silent)")
    results.append(("D4 1:1 chat", "-", "(dropped by webhook filter before _handle — not reproducible here)"))
    run("D5 ยืนยัน with nothing pending", msg("ยืนยัน", NURSE), "(silent or ไม่มีรายการ)")
    run("D6 thanks after applied", msg("ขอบคุณค่ะ"), "(silent)")
    # ── E. expiry & snapshot ──
    _, q = run("E1 report for expiry", msg("แลกเวรเช้า 18 ก.ย. ของธนดล กับ เช้า 19 ก.ย. ของขวัญศิริ"), "summary")
    if q:
        with session() as db:
            cr = db.get(ChangeRequest, q); cr.expires_at = utcnow() - timedelta(minutes=1)
        run("E1b confirm after TTL", postback(f"action=confirm&id={q}"), "หมดเวลายืนยัน")
    _, q = run("E2 report for snapshot mismatch", msg("แลกเวรเช้า 18 ก.ย. ของธนดล กับ เช้า 19 ก.ย. ของขวัญศิริ"), "summary")
    if q:
        ward = Ward(S.sheet_ids[GROUP]); ws = ward.tab("กันยายน2569 (แลก5)")
        old = ws.acell("G18").value; assert old == "ธนดล", old; ws.update_acell("G18", "ทดสอบ")
        try:
            run("E2b confirm after out-of-band edit", postback(f"action=confirm&id={q}"), "ตารางถูกแก้ระหว่างรอ")
            drift = detect_drift(ward, Month(2569, 9))
            results.append(("E3 drift detector", "-", str(drift[:5])))
            print(f"\n### E3 drift detector\n  got: {drift[:5]}")
        finally:
            ws.update_acell("G18", old)
    # ── report ──
    print("\n\n| # | เคส | เวลา | ผลที่ได้ |\n|---|---|---|---|")
    for c, dt, r in results:
        print(f"| {c} | {dt} | {r[:160]} |")


if __name__ == "__main__":
    main()
