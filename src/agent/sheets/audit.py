"""_audit tab (append-only). Never stores LINE userId."""
from __future__ import annotations

from datetime import UTC, datetime

from .client import Ward, with_retry

TAB = "_audit"
HEADER = ["ts", "month", "staff_id", "day", "before", "after", "change_id", "reporter_display_name", "kind", "raw_text",
          "slot"]  # slot: shift code of the cell (grid layout) — used by the drift detector


def ensure_audit(ward: Ward):
    ws = ward.tab(TAB)
    if ws is None:
        ws = with_retry(lambda: ward.ss.add_worksheet(TAB, rows=1000, cols=len(HEADER)))
        with_retry(lambda: ws.append_row(HEADER))
    elif ws.col_count < len(HEADER):  # schema grew (e.g. 'slot' column)
        with_retry(lambda: ws.add_cols(len(HEADER) - ws.col_count))
        with_retry(lambda: ws.update(f"A1:{chr(64 + len(HEADER))}1", [HEADER]))
    return ws


def audit_rows(month: str, cells: list[tuple], change_id: str, reporter: str,
               kind: str, raw_text: str) -> list[list[str]]:
    ts = datetime.now(UTC).isoformat(timespec="seconds")
    out = []
    for c in cells:
        sid, day, before, after = c[:4]
        slot = c[4] if len(c) > 4 else ""
        out.append([ts, month, sid, str(day), before, after, change_id, reporter, kind, raw_text, slot])
    return out


def read_audit(ward: Ward, month: str) -> list[dict[str, str]]:
    ws = ward.tab(TAB)
    if ws is None:
        return []
    rows = with_retry(ws.get_all_values)
    out = []
    for r in rows[1:]:
        if len(r) >= 6 and r[1] == month:
            out.append(dict(zip(HEADER, r + [""] * (len(HEADER) - len(r)))))
    return out
