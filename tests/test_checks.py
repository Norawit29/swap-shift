import pytest

from agent.change.checks import check_edit, check_swap
from agent.change.name_resolver import Staff
from agent.shifts import CellParseError

S = Staff("N001", "สมศรี ใจดี", ("ศรี",))
B = Staff("N002", "บุษบา แสงทอง", ("บี",))
O = Staff("N004", "ศรีวรรณ ดีงาม", ("อ้อ",))


def test_roster_parse(roster, codes):
    assert roster.cell("N001", 3) == "ด" and roster.cell("N002", 5) == "ช"
    assert roster.a1("N001", 3) == (2, 5)  # row 2, col E (staff_id,name,1,2,3)
    assert codes.parse_cell(roster.cell("N004", 3)) == ["ช", "บ"]
    with pytest.raises(CellParseError):
        codes.parse_cell("x")


def test_exchange_rejects_duplicate_code(roster, codes):
    # ศรี already has ช on day 5 → receiving ช would make ชช
    r = check_swap(roster, codes, S, 3, "ด", B, 5, "ช", "live")
    assert not r.ok and "มีเวรเช้าวันที่ 5 ต.ค. อยู่แล้ว" in r.reason


def test_exchange_clean(roster, codes):
    # ศรี day 2 ด ↔ บี day 4 ด : ศรี day 4 empty, บี day 2 ช → ok
    r = check_swap(roster, codes, S, 2, "ด", B, 4, "ด", "published")
    assert r.ok, r.reason
    w = {(x.staff_id, x.day): x.after for x in r.writes}
    assert w == {("N001", 2): "", ("N002", 2): "ชด", ("N002", 4): "", ("N001", 4): "ด"}


def test_mismatch_shows_real_value(roster, codes):
    r = check_swap(roster, codes, S, 3, "บ", B, 5, "ช", "live")
    assert not r.ok and r.reason == 'ศรี วันที่ 3 ต.ค. ตารางระบุ "ด" ไม่ใช่ "บ"'
    r2 = check_swap(roster, codes, S, 4, "ด", B, 5, "ช", "live")  # day 4 empty
    assert 'ตารางระบุ หยุด ไม่ใช่ "ด"' in r2.reason


def test_give(roster, codes):
    r = check_swap(roster, codes, S, 2, "ด", B, None, None, "live")
    assert r.ok and r.lines == ["2 ต.ค. ดึก: ศรี → บี (ยกเวร)"]
    assert {(x.staff_id, x.day): x.after for x in r.writes} == {("N001", 2): "", ("N002", 2): "ชด"}


def test_month_status_and_same_person(roster, codes):
    assert not check_swap(roster, codes, S, 3, "ด", B, 5, "ช", "draft").ok
    assert not check_swap(roster, codes, S, 3, "ด", B, 5, "ช", "closed").ok
    assert "คนเดียวกัน" in check_swap(roster, codes, S, 3, "ด", S, 5, "ช", "live").reason
    assert "ไม่มีวันที่ 32" in check_swap(roster, codes, S, 32, "ด", B, 5, "ช", "live").reason


def test_multi_code_cell_swaps_one_code(roster, codes):
    # อ้อ day 3 = ชบ ; give บ to ศรี (ศรี day 3 = ด) → อ้อ 'ช', ศรี 'ดบ'
    r = check_swap(roster, codes, O, 3, "บ", S, None, None, "live")
    assert r.ok
    assert {(x.staff_id, x.day): x.after for x in r.writes} == {("N004", 3): "ช", ("N001", 3): "ดบ"}


def test_edit(roster, codes):
    r = check_edit(roster, codes, S, 5, "ด", "live")
    assert r.ok and r.writes[0].before == "ช" and r.writes[0].after == "ด"
    assert r.lines == ['5 ต.ค. ศรี: "ช" → "ด"']
    off = check_edit(roster, codes, S, 5, "", "live")
    assert off.ok and off.lines == ['5 ต.ค. ศรี: "ช" → หยุด']
    assert not check_edit(roster, codes, S, 5, "ช", "live").ok  # unchanged
    warn = check_edit(roster, codes, S, 5, "ด", "live", implied_old="บ")
    assert warn.ok and warn.warning


def test_from_words_compounds(codes):
    assert codes.from_words("เช้าบ่าย") == ["ช", "บ"]
    assert codes.from_words("บ่ายดึก") == ["บ", "ด"]
    assert codes.from_words("เช้าดึก") == ["ช", "ด"]
    assert codes.from_words("เช้าบ่ายดึก") == ["ช", "บ", "ด"]
    assert codes.from_words("เช้า บ่าย และ ดึก") == ["ช", "บ", "ด"]
    assert codes.from_words("ดึกเช้า") == ["ด", "ช"]
    assert codes.from_words("บด") == ["บ", "ด"]
    assert codes.from_words("ทั้งวัน") == ["all"]
    assert codes.from_words("conference") == ["conference"]
    assert codes.from_words("xyz") is None


def test_norm_shift_orders_and_all(codes):
    from agent.change.service import _norm_shift

    assert _norm_shift("บ่ายดึก", codes) == "บด"
    assert _norm_shift("ดึกเช้า", codes) == "ชด"
    assert _norm_shift("เช้าบ่ายดึก", codes) == "all"
    assert _norm_shift("ชบด", codes) == "all"
    assert _norm_shift("เช้า", codes) == "ช"
    assert _norm_shift("ทั้งวัน", codes) == "all"
    assert _norm_shift("??", codes) is None
