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


def apply_writes(ward: Ward, month_key: str, writes: list[CellWrite], change_id: str, reporter: str,
                 kind: str, raw_text: str) -> None:
    ws = ward.tab(month_key)
    if ws is None:
        raise KeyError(f"tab {month_key} not found")
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
    body = [{"range": rowcol_to_a1(w.row, w.col), "values": [[w.after]]} for w in writes]
    with_retry(lambda: ws.batch_update(body, value_input_option="RAW"))
    audit = ensure_audit(ward)
    rows = audit_rows(month_key, [(w.staff_id, w.day, w.before, w.after) for w in writes], change_id, reporter,
                      kind, raw_text)
    with_retry(lambda: audit.append_rows(rows, value_input_option="RAW"))
