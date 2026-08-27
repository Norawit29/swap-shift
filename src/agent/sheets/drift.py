"""Drift detector: expected = _planned + _audit replay; compare to live tab. Never auto-revert."""
from __future__ import annotations

from ..thai_date import Month
from .audit import read_audit
from .client import Ward
from .reader import parse_roster


def expected_state(ward: Ward, month: Month) -> dict[tuple[str, int], str]:
    planned = parse_roster(ward.values(f"{month.key}_planned"), month)
    state = {(sid, d): v for sid, row in planned.rows.items() for d, v in row.cells.items()}
    for a in read_audit(ward, month.key):
        try:
            state[(a["staff_id"], int(a["day"]))] = a["after"]
        except (KeyError, ValueError):
            continue
    return state


def detect_drift(ward: Ward, month: Month) -> list[tuple[str, int, str, str]]:
    """→ [(staff_id, day, expected, actual)]"""
    expected = expected_state(ward, month)
    actual = parse_roster(ward.values(month.key), month)
    out = []
    for (sid, d), exp in expected.items():
        act = actual.cell(sid, d) if actual.has(sid) else ""
        if act != exp:
            out.append((sid, d, exp, act))
    for sid, row in actual.rows.items():
        for d, v in row.cells.items():
            if (sid, d) not in expected and v:
                out.append((sid, d, "", v))
    return out


def build_diff(ward: Ward, month: Month) -> tuple[int, dict[str, int]]:
    """Create <month>_diff tab: rows where planned ≠ actual. Returns (n_rows, per-staff delta count)."""
    planned = parse_roster(ward.values(f"{month.key}_planned"), month)
    actual = parse_roster(ward.values(month.key), month)
    rows = [["staff_id", "name", "day", "planned", "actual"]]
    per: dict[str, int] = {}
    for sid, prow in planned.rows.items():
        for d in sorted(prow.cells):
            p = prow.cells[d]
            a = actual.cell(sid, d) if actual.has(sid) else ""
            if p != a:
                rows.append([sid, prow.name, str(d), p, a])
                per[prow.name or sid] = per.get(prow.name or sid, 0) + 1
    title = f"{month.key}_diff"
    ws = ward.tab(title)
    if ws is None:
        ws = ward.ss.add_worksheet(title, rows=max(len(rows) + 5, 20), cols=5)
    else:
        ws.clear()
    ws.update("A1", rows, value_input_option="RAW")
    return len(rows) - 1, per
