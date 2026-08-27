from __future__ import annotations

from ..change.name_resolver import Staff
from .client import Ward, with_retry

TAB = "_staff"


def read_staff(ward: Ward) -> list[Staff]:
    ws = ward.tab(TAB)
    if ws is None:
        return []
    out: list[Staff] = []
    for row in with_retry(ws.get_all_values)[1:]:
        if not row or not row[0].strip():
            continue
        sid = row[0].strip()
        name = row[1].strip() if len(row) > 1 else ""
        nicks = tuple(n.strip() for n in (row[2] if len(row) > 2 else "").split(",") if n.strip())
        active = (row[3].strip().upper() if len(row) > 3 and row[3].strip() else "TRUE") in ("TRUE", "1", "YES")
        out.append(Staff(sid, name, nicks, active))
    return out
