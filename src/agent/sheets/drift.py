"""Drift detector: expected = _planned + _audit replay; compare to live tab. Never auto-revert."""
from __future__ import annotations

from ..thai_date import Month
from .audit import read_audit
from .client import Ward
from .control import read_control
from .layout import layout, parse_values, planned_title, tab_title


def _tabs(ward: Ward, month: Month) -> tuple[str, str]:
    ctl = read_control(ward)
    t, p = tab_title(ward, month, ctl), planned_title(ward, month, ctl)
    if t is None or p is None:
        raise KeyError(month.key)
    return t, p


def expected_state(ward: Ward, month: Month) -> dict[tuple[str, int], str]:
    live, planned_t = _tabs(ward, month)
    planned = parse_values(ward.values(planned_t), month)
    audit = read_audit(ward, month.key)
    if layout() == "grid":
        return replay_grid(planned.cells_map(), audit)
    state = dict(planned.cells_map())
    for a in audit:
        try:
            state[(a["staff_id"], int(a["day"]))] = a["after"]
        except (KeyError, ValueError):
            continue
    return state


def replay_grid(planned: dict[tuple[str, int], str], audit: list[dict[str, str]]) -> dict[tuple[str, int], str]:
    """Grid layout: audit before/after are NAMES in one slot (code in 'slot'). Move that code between people."""
    from ..shifts import load_shifts
    from .grid import base_name

    codes = load_shifts()
    state: dict[tuple[str, int], list[str]] = {k: codes.parse_cell(v) for k, v in planned.items()}
    for a in audit:
        try:
            day, code = int(a["day"]), a.get("slot", "")
        except (KeyError, ValueError):
            continue
        if not code:
            continue  # legacy row without slot — cannot replay reliably
        frm, to = base_name(a.get("before", "")), base_name(a.get("after", ""))
        if frm:
            lst = state.setdefault((frm, day), [])
            if code in lst:
                lst.remove(code)
        if to:
            lst = state.setdefault((to, day), [])
            if code not in lst:
                lst.append(code)
    return {k: codes.serialize(v) for k, v in state.items() if v}


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
