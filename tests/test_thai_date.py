from datetime import date

import pytest

from agent.thai_date import Month, fmt_day, month_index, parse_month

TODAY = date(2026, 8, 27)  # 2569


@pytest.mark.parametrize("text,key", [
    ("2569-10", "2569-10"), ("10/2569", "2569-10"), ("ต.ค.", "2569-10"), ("ตุลาคม", "2569-10"),
    ("ต.ค. 69", "2569-10"), ("ตค", "2569-10"), ("ปิดตาราง ก.ย.", "2569-09"), ("2026-10", "2569-10"),
    ("10/26", "2526-10"),  # 2-digit slash year → 25xx by convention
])
def test_parse_month(text, key):
    assert parse_month(text, today=TODAY).key == key


def test_parse_month_none():
    assert parse_month("", today=TODAY) is None
    assert parse_month("สวัสดี", today=TODAY) is None


def test_month_props():
    m = Month.from_key("2569-10")
    assert m.year_ce == 2026 and m.days == 31 and m.label == "ตุลาคม 2569" and m.abbr == "ต.ค."
    assert m.next().key == "2569-11" and Month(2569, 12).next().key == "2570-01"
    assert Month(2569, 2).days == 28  # 2026 not leap
    assert m.contains(31) and not m.contains(32)
    assert fmt_day(m, 3) == "3 ต.ค."
    assert Month.from_date(TODAY).key == "2569-08"


def test_month_index():
    assert month_index("พ.ย.") == 11 and month_index("12") == 12 and month_index("x") is None


def test_parse_link_command():
    from agent.commands import parse_command

    for t in ("ตาราง", "ตารางเวร", "ขอตารางเวร", "ขอตารางเวรหน่อย", "ลิงก์ตาราง", "ขอ ตารางเวร ค่ะ"):
        c = parse_command(t)
        assert c and c.name == "ตาราง" and c.arg == "", t
    assert parse_command("ตารางเวร ต.ค.").arg == "ต.ค."
    assert parse_command("ขอตารางเวรเดือน 2569-10 หน่อยค่ะ").arg == "2569-10"
    assert parse_command("ตรวจตาราง 2569-10").name == "ตรวจตาราง"
    assert parse_command("ตารางเดือนหน้าออกยัง") is not None  # arg 'หน้าออกยัง' → month parse fails → polite reply
    assert parse_command("แลกเวร ตาราง") is None


def test_roster_link_tag():
    from unittest.mock import MagicMock

    from agent.commands import roster_link

    ward = MagicMock()
    ward.tab.return_value = None  # no _control
    ward.sheet_titles.return_value = ["สิงหาคม 2569"]
    ward.tab_url.return_value = "https://x/#gid=1"
    import os
    os.environ["ROSTER_LAYOUT"] = "grid"
    from agent.settings import get_settings
    get_settings.cache_clear()
    out = roster_link(ward, "ส.ค.", today=date(2026, 8, 27))
    assert "(ยังไม่ประกาศ)" in out and out.endswith("https://x/#gid=1")
