"""Pick roster layout + resolve month → tab title."""
from __future__ import annotations

from ..settings import get_settings
from ..thai_date import Month
from .base import RosterBase
from .client import Ward
from .grid import month_tab_title, parse_grid
from .reader import parse_roster


def layout() -> str:
    return get_settings().roster_layout


def tab_title(ward: Ward, month: Month) -> str | None:
    if layout() == "grid":
        return month_tab_title(ward.sheet_titles(), month)
    return month.key if ward.tab(month.key) is not None else None


def parse_values(values: list[list[str]], month: Month) -> RosterBase:
    return parse_grid(values, month) if layout() == "grid" else parse_roster(values, month)


def load_roster(ward: Ward, month: Month) -> tuple[str, RosterBase] | None:
    title = tab_title(ward, month)
    if title is None:
        return None
    return title, parse_values(ward.values(title), month)
