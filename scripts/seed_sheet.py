"""Seed a ward spreadsheet with _control, _staff, _audit and a demo month from tests/fixtures/roster_2569-10.csv.

usage: python scripts/seed_sheet.py <SPREADSHEET_ID> [2569-10]
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.sheets.audit import ensure_audit  # noqa: E402
from agent.sheets.client import Ward  # noqa: E402
from agent.sheets.control import set_control  # noqa: E402

FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
STAFF = [["staff_id", "full_name_th", "nicknames", "active"],
         ["N001", "สมศรี ใจดี", "ศรี,พี่ศรี", "TRUE"],
         ["N002", "บุษบา แสงทอง", "บี,น้องบี", "TRUE"],
         ["N003", "กมล รักงาน", "กมล", "TRUE"],
         ["N004", "ศรีวรรณ ดีงาม", "อ้อ", "TRUE"]]


def main(sheet_id: str, month: str = "2569-10") -> None:
    ward = Ward(sheet_id)
    ss = ward.ss

    def upsert(title: str, rows: list[list[str]]):
        ws = ward.tab(title)
        if ws is None:
            ws = ss.add_worksheet(title, rows=max(len(rows) + 10, 40), cols=max(len(rows[0]) + 2, 35))
        ws.clear()
        ws.update("A1", rows, value_input_option="RAW")

    upsert("_staff", STAFF)
    with open(FIX / f"roster_{month}.csv", encoding="utf-8", newline="") as f:
        upsert(month, [row for row in csv.reader(f)])
    ensure_audit(ward)
    set_control(ward, {"ward_code": "MED3", "active_months": month, f"status:{month}": "draft"})
    print(f"seeded {ward.url} — tab {month} is draft; send 'ประกาศตาราง {month}' in LINE to publish")


if __name__ == "__main__":
    main(*sys.argv[1:])
