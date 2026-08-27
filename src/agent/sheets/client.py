"""gspread client + per-ward spreadsheet access with retry on 429/5xx."""
from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from functools import lru_cache
from typing import TypeVar

import gspread
from google.oauth2.service_account import Credentials

from ..settings import get_settings

log = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
T = TypeVar("T")


@lru_cache
def gspread_client() -> gspread.Client:
    creds = Credentials.from_service_account_info(get_settings().service_account_info(), scopes=SCOPES)
    return gspread.authorize(creds)


def service_account_email() -> str:
    return str(get_settings().service_account_info().get("client_email", ""))


def with_retry(fn: Callable[[], T], attempts: int = 4) -> T:
    delay = 1.0
    for i in range(attempts):
        try:
            return fn()
        except gspread.exceptions.APIError as e:  # type: ignore[attr-defined]
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code not in (429, 500, 502, 503, 504) or i == attempts - 1:
                raise
            log.warning("sheets api %s, retry in %.1fs", code, delay)
            time.sleep(delay + random.random() * 0.5)
            delay *= 2
    raise RuntimeError("unreachable")


class Ward:
    """One spreadsheet per ward."""

    def __init__(self, spreadsheet_id: str):
        self.id = spreadsheet_id
        self._ss: gspread.Spreadsheet | None = None

    @property
    def ss(self) -> gspread.Spreadsheet:
        if self._ss is None:
            self._ss = with_retry(lambda: gspread_client().open_by_key(self.id))
        return self._ss

    @property
    def url(self) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.id}"

    def tab(self, title: str) -> gspread.Worksheet | None:
        try:
            return with_retry(lambda: self.ss.worksheet(title))
        except gspread.exceptions.WorksheetNotFound:
            return None

    def values(self, title: str) -> list[list[str]]:
        ws = self.tab(title)
        if ws is None:
            raise KeyError(f"tab {title!r} not found")
        return with_retry(ws.get_all_values)

    def tab_url(self, title: str) -> str:
        ws = self.tab(title)
        return f"{self.url}/edit#gid={ws.id}" if ws else self.url


@lru_cache
def ward_for_group(group_id: str) -> Ward | None:
    sid = get_settings().sheet_id_for(group_id)
    return Ward(sid) if sid else None
