"""Grid layout (ER attending sheet) — fixture exported from the real September 2569 tab."""
import csv
from pathlib import Path

import pytest

from agent.change.checks import check_edit, check_swap
from agent.change.name_resolver import Staff
from agent.sheets.base import Move, PlanError
from agent.sheets.grid import base_name, month_tab_title, parse_grid
from agent.thai_date import Month

FIX = Path(__file__).parent / "fixtures" / "grid_2569-09.csv"
M = Month(2569, 9)


@pytest.fixture
def grid():
    with open(FIX, encoding="utf-8", newline="") as f:
        return parse_grid([r for r in csv.reader(f)], M)


def test_parse_real_layout(grid):
    assert grid.cell("จุฑามาศ", 10) == "ช"        # 8.00-16.00 row, Thu 10
    assert grid.cell("ธนดล", 3) == "ช"
    assert grid.cell("อรรถสิทธิ์", 3) == "ชบด"     # On floor + 16-24 + 0-8
    assert grid.cell("ภควดี", 9) == "บด"           # '9*Interhos*' date cell parsed
    assert grid.cell("ธนดล", 18) == "ช"            # '18ems'
    assert grid.cell("คมสันติ", 7) == "ชบด"
    assert grid.cell("ธนดล", 12) == ""
    assert "ธนดล" in grid.names and "วรวรรธน์" in grid.names  # TM suffix stripped
    assert base_name(" สุรีย์ภรณ์ TM ") == "สุรีย์ภรณ์"


def test_swap_moves_names_and_keeps_tm(grid):
    a, b = Staff("จุฑามาศ", "จุฑามาศ"), Staff("ธนดล", "ธนดล")
    from agent.shifts import load_shifts

    r = check_swap(grid, load_shifts(), a, 10, "ช", b, 3, "ช", "live")  # จุฑามาศ ช 10 ↔ ธนดล ช 3
    assert r.ok, r.reason
    w = {(x.row, x.col): (x.before, x.after) for x in r.writes}
    assert w == {(11, 6): ("จุฑามาศ", "ธนดล"), (4, 6): ("ธนดล", "จุฑามาศ")}
    assert r.lines == ["10 ก.ย. เช้า: จุฑามาศ → ธนดล", "3 ก.ย. เช้า: ธนดล → จุฑามาศ"]
    # TM suffix preserved on conference slot
    ws = grid.plan_moves([Move("วรวรรธน์", "ธนดล", 2, "conference")])
    assert ws[0].before == "วรวรรธน์ TM" and ws[0].after == "ธนดล TM"


def test_swap_rejects_when_not_on_shift_or_duplicate(grid):
    from agent.shifts import load_shifts

    codes = load_shifts()
    a, b = Staff("จุฑามาศ", "จุฑามาศ"), Staff("ธนดล", "ธนดล")
    r = check_swap(grid, codes, a, 10, "ด", b, 3, "ช", "live")
    assert not r.ok and 'จุฑามาศ วันที่ 10 ก.ย. ตารางระบุ "ช" ไม่ใช่ "ด"' == r.reason
    # ครองวงศ์ already has ช on day 2 → receiving ช (give) on day 2 rejected
    r2 = check_swap(grid, codes, Staff("ภควดี", "ภควดี"), 2, "ช", Staff("ครองวงศ์", "ครองวงศ์"), None, None, "live")
    assert not r2.ok and "ครองวงศ์ มีเวรเช้าวันที่ 2 ก.ย. อยู่แล้ว" in r2.reason


def test_edit_moves_to_free_slot_or_rejects(grid):
    from agent.shifts import load_shifts

    codes = load_shifts()
    # ธนดล day 12 empty → set ด: 0.00-8.00 row on Sat 12 is empty → ok
    r = check_edit(grid, codes, Staff("ธนดล", "ธนดล"), 12, "ด", "live")
    assert r.ok and r.writes[0].after == "ธนดล" and r.writes[0].before == ""
    # off: clear all slots that day (อรรถสิทธิ์ has 3 on day 3)
    off = check_edit(grid, codes, Staff("อรรถสิทธิ์", "อรรถสิทธิ์"), 3, "", "live")
    assert off.ok and [w.after for w in off.writes] == ["", "", ""] and {w.before for w in off.writes} == {"อรรถสิทธิ์"}
    # no free morning slot on Thu 10 (both morning rows filled) → PlanError → reject
    r3 = check_edit(grid, codes, Staff("ธนดล", "ธนดล"), 10, "ช", "live")
    assert not r3.ok and "ไม่มีช่องว่าง" in r3.reason
    with pytest.raises(PlanError):
        grid.plan_moves([Move("ธนดล", "กิตติ", 12, "ช")])


def test_month_tab_title_rightmost_and_aliases():
    titles = ["_control", "สิงหาคม 2569", "กันยายน2569", "กันยายน2569 (แลก1)", "กันยายน2569 (แลก5)",
              "กันยายน2569 (แลก5)_planned", "กรกฏาคม2569(", "กรกฏาคม2569(2)"]
    assert month_tab_title(titles, Month(2569, 9)) == "กันยายน2569 (แลก5)"
    assert month_tab_title(titles, Month(2569, 7)) == "กรกฏาคม2569(2)"
    assert month_tab_title(titles, Month(2569, 8)) == "สิงหาคม 2569"
    assert month_tab_title(titles, Month(2569, 10)) is None


def test_conference_only_with_conference(grid):
    from agent.shifts import load_shifts

    codes = load_shifts()
    w, s = Staff("วรวรรธน์", "วรวรรธน์"), Staff("สุรีย์ภรณ์", "สุรีย์ภรณ์")
    # conference ↔ conference ok (day 2 วรวรรธน์ TM ↔ day 4 สุรีย์ภรณ์ TM), TM suffix kept
    r = check_swap(grid, codes, w, 2, "conference", s, 4, "conference", "live")
    assert r.ok, r.reason
    assert {x.after for x in r.writes} == {"สุรีย์ภรณ์ TM", "วรวรรธน์ TM"}
    # conference ↔ เช้า rejected
    r2 = check_swap(grid, codes, w, 2, "conference", Staff("ธนดล", "ธนดล"), 3, "ช", "live")
    assert not r2.ok and "แลกได้กับ conference เท่านั้น" in r2.reason
    r3 = check_swap(grid, codes, Staff("ธนดล", "ธนดล"), 3, "ช", w, 2, "conference", "live")
    assert not r3.ok and "conference เท่านั้น" in r3.reason
    # give conference rejected
    r4 = check_swap(grid, codes, w, 2, "conference", s, None, None, "live")
    assert not r4.ok and "ยกให้ไม่ได้" in r4.reason


def test_whole_day_swap(grid):
    from agent.shifts import load_shifts

    codes = load_shifts()
    # อรรถสิทธิ์ 3 ก.ย. = ชบด  ↔  ธนดล 12 ก.ย. = (ว่าง) → give-like exchange rejected? no: exchange needs B codes
    a, b = Staff("อรรถสิทธิ์", "อรรถสิทธิ์"), Staff("คมสันติ", "คมสันติ")
    # อรรถสิทธิ์ 3 (ชบด) ↔ คมสันติ 7 (ชบด): all three codes move both ways
    r = check_swap(grid, codes, a, 3, "all", b, 7, "all", "live")
    assert r.ok, r.reason
    assert r.a_codes == ["ช", "บ", "ด"] and r.b_codes == ["ช", "บ", "ด"]
    assert len(r.writes) == 6 and {w.after for w in r.writes} == {"อรรถสิทธิ์", "คมสันติ"}
    assert r.lines[0] == "3 ก.ย. เช้า: อรรถสิทธิ์ → คมสันติ" and r.lines[-1] == "7 ก.ย. ดึก: คมสันติ → อรรถสิทธิ์"
    # give whole day to someone free that day
    g = check_swap(grid, codes, a, 3, "all", Staff("ธนดล", "ธนดล"), None, None, "live")
    assert not g.ok  # ธนดล already has ช on day 3
    g2 = check_swap(grid, codes, Staff("ภัทรพล", "ภัทรพล"), 4, "all", Staff("ธนดล", "ธนดล"), None, None, "live")
    assert g2.ok and g2.a_codes == ["ช", "บ", "ด"] and len(g2.writes) == 3
    # off day → clear message
    off = check_swap(grid, codes, Staff("ธนดล", "ธนดล"), 12, "all", b, 7, "all", "live")
    assert not off.ok and "ไม่มีเวรให้แลก" in off.reason


def test_tab_title_prefers_pinned_over_rightmost(monkeypatch):
    from unittest.mock import MagicMock

    from agent.sheets import layout as L

    monkeypatch.setenv("ROSTER_LAYOUT", "grid")
    from agent.settings import get_settings

    get_settings.cache_clear()
    ward = MagicMock()
    ward.sheet_titles.return_value = ["กันยายน2569 (แลก5)", "กันยายน2569", "กันยายน2569 (แลก4)"]  # live moved to front
    ward.tab.side_effect = lambda t: MagicMock() if t in ward.sheet_titles.return_value else None
    # without a pin the rightmost (stale) tab wins — the bug
    assert L.tab_title(ward, M, {}) == "กันยายน2569 (แลก4)"
    # pinned in _control → correct tab regardless of order
    assert L.tab_title(ward, M, {"tab:2569-09": "กันยายน2569 (แลก5)"}) == "กันยายน2569 (แลก5)"
    # pin pointing at a deleted tab falls back
    assert L.tab_title(ward, M, {"tab:2569-09": "หายไป"}) == "กันยายน2569 (แลก4)"


def test_label_column_autodetected(grid):
    import csv

    from agent.sheets.grid import detect_label_col
    from agent.shifts import load_shifts

    codes = load_shifts()
    with open(FIX, encoding="utf-8", newline="") as f:
        rows = [r for r in csv.reader(f)]
    assert detect_label_col(rows, codes) == 2 and grid.label_col == 2 and grid.day_cols == (3, 9)
    # same sheet shifted one column left (labels in A) — as in the ตุลาคม2569 tab
    shifted = [r[1:] for r in rows]
    g2 = parse_grid(shifted, M)
    assert g2.label_col == 1 and g2.day_cols == (2, 8)
    assert g2.cell("จุฑามาศ", 10) == grid.cell("จุฑามาศ", 10) == "ช"
    w = g2.plan_moves([Move("จุฑามาศ", "ธนดล", 10, "ช")])
    assert (w[0].row, w[0].col) == (11, 5)  # one column left of the original (11, 6)
