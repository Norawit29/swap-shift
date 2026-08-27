"""Verify service-account access + roster parsing for every SHEET_ID_MAP entry (or a given sheet id).
usage: python scripts/check_sheet.py [SPREADSHEET_ID] [2569-09]
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.settings import get_settings  # noqa: E402
from agent.sheets.client import Ward, service_account_email  # noqa: E402
from agent.sheets.control import read_control  # noqa: E402
from agent.sheets.layout import load_roster  # noqa: E402
from agent.sheets.reader import validate_roster  # noqa: E402
from agent.sheets.staff import read_staff  # noqa: E402
from agent.shifts import load_shifts  # noqa: E402
from agent.thai_date import Month  # noqa: E402


def main(argv: list[str]) -> int:
    s = get_settings()
    print(f"service account: {service_account_email()}")
    print(f"layout: {s.roster_layout}")
    ids = [argv[0]] if argv else list(s.sheet_ids.values())
    if not ids:
        print("no SHEET_ID_MAP and no id given")
        return 1
    month = Month.from_key(argv[1]) if len(argv) > 1 else Month.from_date(date.today())
    rc = 0
    for sid in ids:
        ward = Ward(sid)
        try:
            titles = ward.sheet_titles()
        except Exception as e:  # noqa: BLE001
            print(f"✗ {sid}: cannot open — {type(e).__name__}: {e}\n  → share the sheet to the service account as Editor")
            rc = 1
            continue
        print(f"✓ {sid}: {len(titles)} tabs — {titles[:6]}{' …' if len(titles) > 6 else ''}")
        ctl = read_control(ward)
        print(f"  _control: {ctl or '(missing — will be created on first ประกาศตาราง)'}")
        print(f"  _staff: {len(read_staff(ward))} rows")
        loaded = load_roster(ward, month)
        if loaded is None:
            print(f"  ✗ no tab found for {month.label}")
            rc = 1
            continue
        title, roster = loaded
        names = list(roster.names)
        print(f"  {month.label} → tab {title!r}: {len(names)} people: {names[:8]}{' …' if len(names) > 8 else ''}")
        errors = validate_roster(roster, set(), load_shifts())
        print(f"  ตรวจตาราง: {'OK' if not errors else errors[:5]}")
        # write probe: can we edit? (touch nothing — check permissions via drive metadata)
        try:
            perms = ward.ss.list_permissions()
            me = service_account_email()
            role = next((p.get("role") for p in perms if p.get("emailAddress") == me), None)
            print(f"  permission of service account: {role or 'not listed (maybe via link/domain)'}")
        except Exception as e:  # noqa: BLE001
            print(f"  (permission check skipped: {e})")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
