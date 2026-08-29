"""Ward read cache — the Sheets API allows 60 reads/min/user (see docs/TEST-REPORT bug #2)."""
from unittest.mock import MagicMock

from agent.sheets.client import TTLCache, Ward


def _ward(monkeypatch, rows):
    w = Ward("SID")
    ws = MagicMock()
    ws.title = "tab"
    ws.id = 1
    ws.get_all_values.return_value = rows
    ss = MagicMock()
    ss.worksheets.return_value = [ws]
    monkeypatch.setattr(type(w), "ss", property(lambda self: ss))
    return w, ws, ss


def test_values_and_metadata_are_cached_until_invalidated(monkeypatch):
    w, ws, ss = _ward(monkeypatch, [["a"]])
    assert w.values("tab") == [["a"]]
    for _ in range(5):
        w.values("tab")
        w.tab("tab")
        w.sheet_titles()
        w.tab_by_id(1)
    assert ws.get_all_values.call_count == 1 and ss.worksheets.call_count == 1
    w.invalidate("tab")
    w.values("tab")
    assert ws.get_all_values.call_count == 2 and ss.worksheets.call_count == 2


def test_ttl_zero_always_reads(monkeypatch):
    w, ws, _ = _ward(monkeypatch, [["a"]])
    w.values("tab", ttl=0)
    w.values("tab", ttl=0)
    assert ws.get_all_values.call_count == 2


def test_ttl_cache_expiry(monkeypatch):
    import itertools

    c = TTLCache()
    clock = itertools.count(0, 10)
    monkeypatch.setattr("agent.sheets.client.time.monotonic", lambda: next(clock))
    c.put("k", 1)          # t=0
    assert c.get("k", 60) == 1   # t=10
    assert c.get("k", 5) is None  # t=20 → older than ttl
