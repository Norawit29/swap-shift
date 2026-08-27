"""Protect roster tabs after publish: service account is sole editor. Owner can bypass — see PLAN §4."""
from __future__ import annotations

import logging

from .client import Ward, service_account_email, with_retry

log = logging.getLogger(__name__)


def protect_tab(ward: Ward, title: str) -> None:
    ws = ward.tab(title)
    if ws is None:
        raise KeyError(title)
    for p in with_retry(lambda: ws.list_protected_ranges()):  # replace existing sheet-level protection
        pid = p.get("protectedRangeId")
        if pid and "range" in p and set(p["range"].keys()) <= {"sheetId"}:
            with_retry(lambda pid=pid: ws.delete_protected_range(pid))
    body = {"requests": [{"addProtectedRange": {"protectedRange": {
        "range": {"sheetId": ws.id},
        "description": "managed by line-swap-agent — edit via bot only",
        "warningOnly": False,
        "editors": {"users": [service_account_email()], "domainUsersCanEdit": False},
    }}}]}
    with_retry(lambda: ward.ss.batch_update(body))
    log.info("protected tab %s", title)


def is_protected(ward: Ward, title: str) -> bool:
    ws = ward.tab(title)
    if ws is None:
        return False
    return any("range" in p and set(p["range"].keys()) <= {"sheetId"} for p in with_retry(ws.list_protected_ranges))
