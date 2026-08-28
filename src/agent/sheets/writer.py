"""Deterministic writer: re-read cells (optimistic lock) → batch write cells + audit rows."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from gspread.utils import rowcol_to_a1

from ..settings import get_settings
from .audit import audit_rows, ensure_audit
from .client import Ward, with_retry

log = logging.getLogger(__name__)


class SnapshotMismatch(Exception):
    pass


@dataclass(frozen=True)
class CellWrite:
    staff_id: str
    day: int
    row: int
    col: int
    before: str  # value at request time (snapshot)
    after: str
    code: str = ""  # grid layout: shift code of the slot (for drift replay)


def apply_writes(ward: Ward, tab: str, writes: list[CellWrite], change_id: str, reporter: str,
                 kind: str, raw_text: str, month_key: str | None = None) -> None:
    month_key = month_key or tab
    ws = ward.tab(tab)
    if ws is None:
        raise KeyError(f"tab {tab} not found")
    # optimistic lock: re-read exactly the affected cells
    ranges = [rowcol_to_a1(w.row, w.col) for w in writes]
    current = with_retry(lambda: ws.batch_get(ranges))
    for w, got in zip(writes, current):
        val = (got[0][0] if got and got[0] else "").strip()
        if val != w.before:
            raise SnapshotMismatch(f"{w.staff_id} day {w.day}: expected {w.before!r}, sheet has {val!r}")
    if get_settings().dry_run:
        log.info("DRY_RUN: would write %s", [(w.staff_id, w.day, w.before, w.after) for w in writes])
        return
    colors = None
    if _grid_colors():
        from .colors import person_colors, read_cell_colors

        try:
            colors = person_colors(read_cell_colors(ward, tab))  # read BEFORE names move
        except Exception as e:  # noqa: BLE001
            log.warning("colour read failed: %s", e)
    body = [{"range": rowcol_to_a1(w.row, w.col), "values": [[w.after]]} for w in writes]
    with_retry(lambda: ws.batch_update(body, value_input_option="RAW"))
    if colors is not None:
        from .colors import sync_colors

        sync_colors(ward, tab, writes, colors)
    audit = ensure_audit(ward)
    rows = audit_rows(month_key, [(w.staff_id, w.day, w.before, w.after, w.code) for w in writes], change_id,
                      reporter, kind, raw_text)
    with_retry(lambda: audit.append_rows(rows, value_input_option="RAW"))


def _grid_colors() -> bool:
    from .colors import is_grid

    return is_grid()
