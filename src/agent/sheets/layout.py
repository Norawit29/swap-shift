"""Pick roster layout + resolve month → tab title."""
from __future__ import annotations

from ..settings import get_settings
from ..thai_date import Month
from .base import RosterBase
from .client import Ward
from .control import read_control
from .grid import month_tab_title, parse_grid
from .reader import parse_roster


def layout() -> str:
    return get_settings().roster_layout


def tab_title(ward: Ward, month: Month, control: dict[str, str] | None = None) -> str | None:
    """Grid layout: the tab pinned in _control at publish time wins; otherwise the rightmost matching tab.

    The pin matters because tabs get reordered (go-live moves the live month to the front), which would
    otherwise make the "rightmost" heuristic pick an old revision tab.
    """
    if layout() != "grid":
        return month.key if ward.tab(month.key) is not None else None
    ctl = control if control is not None else read_control(ward)
    pinned = ctl.get(f"tab:{month.key}", "").strip()
    if pinned and ward.tab(pinned) is not None:
        return pinned
    return month_tab_title(ward.sheet_titles(), month)


def parse_values(values: list[list[str]], month: Month) -> RosterBase:
    return parse_grid(values, month) if layout() == "grid" else parse_roster(values, month)


def load_roster(ward: Ward, month: Month, control: dict[str, str] | None = None) -> tuple[str, RosterBase] | None:
    title = tab_title(ward, month, control)
    if title is None:
        return None
    return title, parse_values(ward.values(title), month)
