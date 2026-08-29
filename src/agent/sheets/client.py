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


class TTLCache:
    """Tiny in-process cache — the Sheets API allows only 60 reads/min/user."""

    def __init__(self) -> None:
        self._d: dict[str, tuple[float, object]] = {}

    def get(self, key: str, ttl: float):
        if ttl <= 0:
            return None
        hit = self._d.get(key)
        if hit and (time.monotonic() - hit[0]) < ttl:
            return hit[1]
        return None

    def put(self, key: str, value):
        self._d[key] = (time.monotonic(), value)
        return value

    def drop(self, *prefixes: str) -> None:
        if not prefixes:
            self._d.clear()
            return
        for k in [k for k in self._d if k.startswith(prefixes)]:
            self._d.pop(k, None)


class Ward:
    """One spreadsheet per ward. Reads go through a short TTL cache; writers must call invalidate()."""

    def __init__(self, spreadsheet_id: str):
        self.id = spreadsheet_id
        self._ss: gspread.Spreadsheet | None = None
        self._cache = TTLCache()

    # ── cache plumbing ────────────────────────────────────────
    def invalidate(self, *titles: str) -> None:
        """After a write: drop cached values (and metadata, since ids/titles may have changed)."""
        if titles:
            for t in titles:
                self._cache.drop(f"values:{t}", f"colors:{t}")
        else:
            self._cache.drop("values:", "colors:")
        self._cache.drop("meta:")

    def _meta(self, key: str, fn, ttl: float | None = None):
        ttl = get_settings().cache_ttl if ttl is None else ttl
        hit = self._cache.get(key, ttl)
        return hit if hit is not None else self._cache.put(key, fn())

    @property
    def ss(self) -> gspread.Spreadsheet:
        if self._ss is None:
            self._ss = with_retry(lambda: gspread_client().open_by_key(self.id))
        return self._ss

    @property
    def url(self) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.id}"

    def worksheets(self) -> list[gspread.Worksheet]:
        return self._meta("meta:all", lambda: with_retry(self.ss.worksheets))

    def tab(self, title: str) -> gspread.Worksheet | None:
        for ws in self.worksheets():
            if ws.title == title:
                return ws
        return None

    def values(self, title: str, ttl: float | None = None) -> list[list[str]]:
        ws = self.tab(title)
        if ws is None:
            raise KeyError(f"tab {title!r} not found")
        ttl = get_settings().cache_ttl if ttl is None else ttl
        key = f"values:{title}"
        hit = self._cache.get(key, ttl)
        return hit if hit is not None else self._cache.put(key, with_retry(ws.get_all_values))

    def cached(self, key: str, ttl: float, fn):
        """Generic cached read (used for cell colours)."""
        hit = self._cache.get(key, ttl)
        return hit if hit is not None else self._cache.put(key, fn())

    def tab_by_id(self, sheet_id: int) -> gspread.Worksheet | None:
        """Sheet ids survive renames — the reliable way to point at a tab."""
        for ws in self.worksheets():
            if ws.id == sheet_id:
                return ws
        return None

    def sheet_titles(self) -> list[str]:
        return [ws.title for ws in self.worksheets()]

    def tab_url(self, title: str) -> str:
        ws = self.tab(title)
        return f"{self.url}/edit#gid={ws.id}" if ws else self.url


@lru_cache
def ward_for_group(group_id: str) -> Ward | None:
    sid = get_settings().sheet_id_for(group_id)
    return Ward(sid) if sid else None
