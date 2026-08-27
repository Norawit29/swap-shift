"""Drift detector: expected = _planned + _audit replay; compare to live tab. Never auto-revert."""
from __future__ import annotations

from ..thai_date import Month
from .audit import read_audit
from .client import Ward
from .layout import parse_values, tab_title


def _tabs(ward: Ward, month: Month) -> tuple[str, str]:
    t = tab_title(ward, month)
    if t is None:
        raise KeyError(month.key)
    return t, f"{t}_planned"


def expected_state(ward: Ward, month: Month) -> dict[tuple[str, int], str]:
    live, planned_t = _tabs(ward, month)
    planned = parse_values(ward.values(planned_t), month)
    state = dict(planned.cells_map())
    for a in read_audit(ward, month.key):
        try:
            state[(a["staff_id"], int(a["day"]))] = a["after"]
        except (KeyError, ValueError):
            continue
    return state


def detect_drift(ward: Ward, month: Month) -> list[tuple[str, int, str, str]]:
    """→ [(staff_id, day, expected, actual)]"""
    expected = expected_state(ward, month)
    live, _ = _tabs(ward, month)
    actual_map = parse_values(ward.values(live), month).cells_map()
    out = []
    for (sid, d), exp in expected.items():
        act = actual_map.get((sid, d), "")
        if act != exp:
            out.append((sid, d, exp, act))
    for (sid, d), v in actual_map.items():
        if (sid, d) not in expected and v:
            out.append((sid, d, "", v))
    return out


def build_diff(ward: Ward, month: Month) -> tuple[int, dict[str, int]]:
    """Create <month>_diff tab: rows where planned ≠ actual. Returns (n_rows, per-staff delta count)."""
    live, planned_t = _tabs(ward, month)
    planned = parse_values(ward.values(planned_t), month)
    actual = parse_values(ward.values(live), month).cells_map()
    pmap = planned.cells_map()
    rows = [["staff_id", "name", "day", "planned", "actual"]]
    per: dict[str, int] = {}
    for (sid, d) in sorted(set(pmap) | set(actual)):
        p, a = pmap.get((sid, d), ""), actual.get((sid, d), "")
        if p != a:
            name = planned.names.get(sid, sid)
            rows.append([sid, name, str(d), p, a])
            per[name] = per.get(name, 0) + 1
    title = f"{month.key}_diff"
    ws = ward.tab(title)
    if ws is None:
        ws = ward.ss.add_worksheet(title, rows=max(len(rows) + 5, 20), cols=5)
    else:
        ws.clear()
    ws.update("A1", rows, value_input_option="RAW")
    return len(rows) - 1, per
