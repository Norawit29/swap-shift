"""Protect roster tabs after publish: service account is sole editor. Owner can bypass — see PLAN §4."""
from __future__ import annotations

import logging

from .client import Ward, service_account_email, with_retry

log = logging.getLogger(__name__)


def _sheet_level_protections(ward: Ward, sheet_id: int) -> list[int]:
    meta = with_retry(lambda: ward.ss.fetch_sheet_metadata({"fields": "sheets(properties.sheetId,protectedRanges)"}))
    for sh in meta.get("sheets", []):
        if sh.get("properties", {}).get("sheetId") != sheet_id:
            continue
        return [p["protectedRangeId"] for p in sh.get("protectedRanges", [])
                if set(p.get("range", {}).keys()) <= {"sheetId"}]
    return []


def protect_tab(ward: Ward, title: str) -> None:
    ws = ward.tab(title)
    if ws is None:
        raise KeyError(title)
    reqs = [{"deleteProtectedRange": {"protectedRangeId": pid}} for pid in _sheet_level_protections(ward, ws.id)]
    reqs.append({"addProtectedRange": {"protectedRange": {
        "range": {"sheetId": ws.id},
        "description": "managed by line-swap-agent — edit via bot only",
        "warningOnly": False,
        "editors": {"users": [service_account_email()], "domainUsersCanEdit": False},
    }}})
    with_retry(lambda: ward.ss.batch_update({"requests": reqs}))
    log.info("protected tab %s", title)


def is_protected(ward: Ward, title: str) -> bool:
    ws = ward.tab(title)
    return bool(ws) and bool(_sheet_level_protections(ward, ws.id))
