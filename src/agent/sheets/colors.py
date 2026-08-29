"""Grid layout: each staff member's cells carry a personal background colour — keep it in sync with the name."""
from __future__ import annotations

import logging
from collections import Counter

from ..shifts import load_shifts
from .client import Ward, with_retry
from .grid import MAX_LABEL_COL, base_name
from .writer import CellWrite

log = logging.getLogger(__name__)
WHITE = {"red": 1, "green": 1, "blue": 1}
Color = tuple[float, float, float]


def _rgb(c: dict | None) -> Color:
    c = c or {}
    return (round(c.get("red", 0), 3), round(c.get("green", 0), 3), round(c.get("blue", 0), 3))


def read_cell_colors(ward: Ward, title: str) -> dict[tuple[int, int], tuple[str, Color]]:
    """→ {(row, col): (raw value, rgb)} for the day columns of the whole tab (one API call)."""
    meta = with_retry(lambda: ward.ss.fetch_sheet_metadata({
        "includeGridData": True, "ranges": [f"'{title}'"],
        "fields": "sheets.data(startRow,startColumn,rowData.values(formattedValue,effectiveFormat.backgroundColor))",
    }))
    out: dict[tuple[int, int], tuple[str, Color]] = {}
    for sh in meta.get("sheets", []):
        for block in sh.get("data", []):
            r0, c0 = block.get("startRow", 0), block.get("startColumn", 0)
            for i, row in enumerate(block.get("rowData", [])):
                for j, cell in enumerate(row.get("values", [])):
                    r, c = r0 + i + 1, c0 + j + 1
                    if c > MAX_LABEL_COL - 2:  # skip the leading label columns; layout may be shifted
                        bg = cell.get("effectiveFormat", {}).get("backgroundColor")
                        out[(r, c)] = (cell.get("formattedValue", "") or "", _rgb(bg))
    return out


def person_colors(cells: dict[tuple[int, int], tuple[str, Color]]) -> dict[str, Color]:
    """Most common non-white colour per person name."""
    votes: dict[str, Counter] = {}
    for (_, _), (val, rgb) in cells.items():
        name = base_name(val)
        if name and rgb != (1.0, 1.0, 1.0):
            votes.setdefault(name, Counter())[rgb] += 1
    return {n: c.most_common(1)[0][0] for n, c in votes.items()}


def color_requests(sheet_id: int, writes: list[CellWrite], colors: dict[str, Color]) -> list[dict]:
    reqs = []
    for w in writes:
        name = base_name(w.after)
        if name:
            rgb = colors.get(name)
            if rgb is None:
                continue  # unknown colour → leave as is
            bg = {"red": rgb[0], "green": rgb[1], "blue": rgb[2]}
        else:
            bg = WHITE
        reqs.append({"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": w.row - 1, "endRowIndex": w.row,
                      "startColumnIndex": w.col - 1, "endColumnIndex": w.col},
            "cell": {"userEnteredFormat": {"backgroundColor": bg}},
            "fields": "userEnteredFormat.backgroundColor",
        }})
    return reqs


def sync_colors(ward: Ward, title: str, writes: list[CellWrite], colors: dict[str, Color]) -> int:
    """Apply person colours to written cells. Best effort — never raises."""
    try:
        ws = ward.tab(title)
        reqs = color_requests(ws.id, writes, colors)
        if reqs:
            with_retry(lambda: ward.ss.batch_update({"requests": reqs}))
        return len(reqs)
    except Exception as e:  # noqa: BLE001
        log.warning("colour sync failed for %s: %s", title, e)
        return 0


def is_grid() -> bool:
    from ..settings import get_settings

    return get_settings().roster_layout == "grid" and bool(load_shifts().grid_rows)
