"""_control tab: key/value. Month lifecycle draft → published → live → closed."""
from __future__ import annotations

from datetime import datetime, timezone

from ..thai_date import Month
from .client import Ward, with_retry

TAB = "_control"
STATUSES = ("draft", "published", "live", "closed")
WRITABLE = {"published", "live"}


def read_control(ward: Ward) -> dict[str, str]:
    ws = ward.tab(TAB)
    if ws is None:
        return {}
    out = {}
    for row in with_retry(ws.get_all_values):
        if len(row) >= 2 and row[0].strip():
            out[row[0].strip()] = row[1].strip()
    return out


def set_control(ward: Ward, updates: dict[str, str]) -> None:
    ws = ward.tab(TAB)
    if ws is None:
        ws = with_retry(lambda: ward.ss.add_worksheet(TAB, rows=50, cols=2))
        with_retry(lambda: ws.update("A1:B1", [["key", "value"]]))
    rows = with_retry(ws.get_all_values)
    keys = {r[0].strip(): i + 1 for i, r in enumerate(rows) if r and r[0].strip()}
    batch = []
    append = []
    for k, v in updates.items():
        if k in keys:
            batch.append({"range": f"B{keys[k]}", "values": [[v]]})
        else:
            append.append([k, v])
    if batch:
        with_retry(lambda: ws.batch_update(batch))
    if append:
        with_retry(lambda: ws.append_rows(append))


def month_status(control: dict[str, str], month: Month) -> str:
    return control.get(f"status:{month.key}", "draft" if month.key in active_months(control) else "")


def active_months(control: dict[str, str]) -> list[str]:
    return [m.strip() for m in control.get("active_months", "").split(",") if m.strip()]


def set_status(ward: Ward, month: Month, status: str, by: str = "") -> None:
    assert status in STATUSES
    upd = {f"status:{month.key}": status}
    ctl = read_control(ward)
    months = active_months(ctl)
    if status in ("published", "live") and month.key not in months:
        months.append(month.key)
        upd["active_months"] = ",".join(sorted(months))
    if status == "published":
        upd[f"published_at:{month.key}"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        upd[f"published_by:{month.key}"] = by
    if status == "closed":
        upd["active_months"] = ",".join(m for m in months if m != month.key)
    set_control(ward, upd)


def current_month(control: dict[str, str], today_month: Month) -> Month:
    """Month to assume when a report gives no month: today's if active, else first active."""
    months = active_months(control)
    if today_month.key in months or not months:
        return today_month
    return Month.from_key(months[0])
