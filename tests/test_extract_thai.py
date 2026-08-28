"""Recorded fixtures from prompts/extract_examples.jsonl — schema validity + end-to-end service flow with a fake LLM.
No live OpenAI calls in CI."""
import json
from datetime import date
from pathlib import Path

import pytest

from agent.change.service import ChangeService, Incoming
from agent.db import init_db, session
from agent.llm.schemas import ClassifyResult, EditExtraction, SwapExtraction

EX = Path(__file__).resolve().parents[1] / "prompts" / "extract_examples.jsonl"
EXAMPLES = [json.loads(l) for l in EX.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_examples_cover_required_cases():
    kinds = {e["kind"] for e in EXAMPLES}
    assert kinds == {"swap", "classify", "edit"}
    texts = " ".join(e["text"] for e in EXAMPLES)
    assert "ok ค่ะ" in texts and len(EXAMPLES) >= 30


@pytest.mark.parametrize("ex", [e for e in EXAMPLES if e["kind"] == "swap"], ids=lambda e: e["text"][:25])
def test_swap_examples_validate(ex):
    r = SwapExtraction.model_validate(ex["expected"])
    assert r.a_name or "a_name" in r.missing
    assert r.b_name or "b_name" in r.missing
    if r.swap_type == "give":
        assert r.b_day is None and r.b_shift is None


def test_other_schemas():
    for e in EXAMPLES:
        if e["kind"] == "classify":
            ClassifyResult.model_validate({**e["expected"], "confidence": 0.9})
        if e["kind"] == "edit":
            EditExtraction.model_validate(e["expected"])


# ── end-to-end with fake LLM + fake ward ──────────────────────────────

class FakeLLM:
    def __init__(self, swap=None, edit=None):
        self._swap, self._edit = swap, edit

    def classify(self, text):
        return ClassifyResult(intent="swap_report", confidence=0.9)

    def extract_swap(self, text, months, today=None):
        return SwapExtraction.model_validate(self._swap)

    def extract_edit(self, text, months, today=None):
        return EditExtraction.model_validate(self._edit)


class FakeWard:
    def __init__(self, roster_values, control):
        self.rows = {"2569-10": roster_values,
                     "_control": [[k, v] for k, v in control.items()],
                     "_audit": [["ts"]],
                     "_staff": [["staff_id", "full_name_th", "nicknames", "active"],
                                ["N001", "สมศรี ใจดี", "ศรี,พี่ศรี", "TRUE"], ["N002", "บุษบา แสงทอง", "บี,น้องบี", "TRUE"],
                                ["N004", "ศรีวรรณ ดีงาม", "อ้อ", "TRUE"]]}
        self.written = []

    def tab(self, title):
        if title not in self.rows:
            return None
        from unittest.mock import MagicMock

        ws = MagicMock()
        ws.get_all_values.return_value = self.rows[title]
        ws.batch_get.side_effect = lambda ranges: [[[self._cell(title, r)]] for r in ranges]
        ws.batch_update.side_effect = lambda body, **kw: self.written.extend(body)
        return ws

    def _cell(self, title, a1):
        from gspread.utils import a1_to_rowcol

        r, c = a1_to_rowcol(a1)
        row = self.rows[title][r - 1]
        return row[c - 1] if len(row) >= c else ""

    def values(self, title):
        if title not in self.rows:
            raise KeyError(title)
        return self.rows[title]

    def tab_url(self, title):
        return f"https://docs.google.com/spreadsheets/d/FAKE/edit#gid={abs(hash(title)) % 1000}"


EX_SWAP = dict(swap_type="exchange", a_name="ศรี", a_day=2, a_month="2569-10", a_shift="ด", b_name="บี", b_day=4,
               b_month="2569-10", b_shift="ด", missing=[], clarifying_question_th=None)
TODAY = date(2026, 10, 1)


def _svc(roster_values, llm, status="live"):
    init_db()
    ward = FakeWard(roster_values, {"active_months": "2569-10", "status:2569-10": status})
    return ward, llm


def test_e2e_report_confirm_applies(roster_values):
    ward, llm = _svc(roster_values, FakeLLM(swap=EX_SWAP))
    with session() as db:
        svc = ChangeService(ward, llm, db)
        r = svc.handle_swap_report(Incoming("C1", "U1", "ศรี", "แลกเวร...", TODAY))
        assert r.quick_reply_id and "2 ต.ค. ดึก: ศรี → บี" in r.text and "4 ต.ค. ดึก: บี → ศรี" in r.text
        cid = r.quick_reply_id
        assert svc.confirm(cid, "U2").text == "เฉพาะผู้แจ้งเท่านั้น"
        ok = svc.confirm(cid, "U1")
        assert ok.text.startswith("📋 อัปเดตตารางแล้ว #" + cid)
        assert "📅 https://docs.google.com/spreadsheets/d/FAKE" in ok.text
        assert {b["range"]: b["values"][0][0] for b in ward.written} == {"D2": "", "D3": "ชด", "F3": "", "F2": "ด"}
        assert svc.confirm(cid, "U1").text == "ไม่มีรายการรอยืนยัน"  # already applied
        from agent.change.models import ChangeRequest

        cr = db.get(ChangeRequest, cid)
        assert cr.state == "APPLIED" and cr.reporter_line_id is None


def test_e2e_reject_shows_roster_value(roster_values):
    ward, llm = _svc(roster_values, FakeLLM(swap={**EX_SWAP, "a_shift": "ช"}))
    with session() as db:
        r = ChangeService(ward, llm, db).handle_swap_report(Incoming("C1", "U1", "ศรี", "x", TODAY))
        assert r.quick_reply_id is None and 'ศรี วันที่ 2 ต.ค. ตารางระบุ "ด" ไม่ใช่ "ช"' in r.text


def test_e2e_clarify_then_cancel_after_2_rounds(roster_values):
    ex = {**EX_SWAP, "a_name": None, "missing": ["a_name"], "clarifying_question_th": "แลกของใครคะ"}
    ward, llm = _svc(roster_values, FakeLLM(swap=ex))
    with session() as db:
        svc = ChangeService(ward, llm, db)
        r1 = svc.handle_swap_report(Incoming("C1", "U1", "ศรี", "ขอแลก", TODAY))
        assert r1.text.startswith("❓") and "แลกของใครคะ" in r1.text
        pending = svc.open_request("U1")
        assert pending.state == "PENDING_CLARIFICATION"
        r2 = svc.handle_swap_report(Incoming("C1", "U1", "ศรี", "อีกที", TODAY), pending)
        assert r2.text.startswith("❓")
        r3 = svc.handle_swap_report(Incoming("C1", "U1", "ศรี", "อีกที", TODAY), pending)
        assert r3.text.startswith("รบกวนพิมพ์ใหม่")
        assert pending.state == "CANCELLED"


def test_e2e_ambiguous_name_asks(roster_values):
    ex = {**EX_SWAP, "a_name": "ศ"}
    ward, llm = _svc(roster_values, FakeLLM(swap=ex))
    with session() as db:
        r = ChangeService(ward, llm, db).handle_swap_report(Incoming("C1", "U1", "ศรี", "x", TODAY))
        assert "หมายถึงใครคะ" in r.text and "ศรี" in r.text and "อ้อ" in r.text


def test_e2e_cross_month_and_draft(roster_values):
    ward, llm = _svc(roster_values, FakeLLM(swap={**EX_SWAP, "b_month": "2569-11"}))
    with session() as db:
        assert "ข้ามเดือน" in ChangeService(ward, llm, db).handle_swap_report(Incoming("C1", "U1", "ศรี", "x", TODAY)).text
    ward, llm = _svc(roster_values, FakeLLM(swap=EX_SWAP), status="draft")
    with session() as db:
        assert "ยังไม่ประกาศ" in ChangeService(ward, llm, db).handle_swap_report(Incoming("C1", "U1", "ศรี", "x", TODAY)).text


def test_e2e_snapshot_mismatch(roster_values):
    ward, llm = _svc(roster_values, FakeLLM(swap=EX_SWAP))
    with session() as db:
        svc = ChangeService(ward, llm, db)
        cid = svc.handle_swap_report(Incoming("C1", "U1", "ศรี", "x", TODAY)).quick_reply_id
        ward.rows["2569-10"][1][3] = "ช"  # someone edited ศรี day 2 out-of-band
        assert "ตารางถูกแก้ระหว่างรอ" in svc.confirm(cid, "U1").text
        assert ward.written == []


def test_e2e_edit(roster_values):
    ed = dict(target_name="พี่ศรี", day=5, month="2569-10", new_shift="ด", missing=[], clarifying_question_th=None)
    ward, llm = _svc(roster_values, FakeLLM(edit=ed))
    with session() as db:
        svc = ChangeService(ward, llm, db)
        r = svc.handle_edit(Incoming("C1", "UH", "หัวหน้า", "เปลี่ยนพี่ศรี วันที่ 5 เป็นดึก", TODAY))
        assert r.quick_reply_id and '5 ต.ค. ศรี: "ช" → "ด"' in r.text
        assert svc.confirm(r.quick_reply_id, "UH").text.startswith("📋")
        assert ward.written == [{"range": "G2", "values": [["ด"]]}]
