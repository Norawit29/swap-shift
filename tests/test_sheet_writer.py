from unittest.mock import MagicMock

import pytest

from agent.sheets.writer import CellWrite, SnapshotMismatch, apply_writes


def _ward(batch_get):
    ws = MagicMock()
    ws.batch_get.return_value = batch_get
    audit = MagicMock()
    ward = MagicMock()
    ward.tab.side_effect = lambda t: ws if t == "2569-10" else audit
    return ward, ws, audit


def test_batch_write_and_audit(monkeypatch):
    ward, ws, audit = _ward([[["ด"]], [["บ"]]])
    writes = [CellWrite("N001", 3, 2, 5, "ด", ""), CellWrite("N002", 3, 3, 5, "บ", "บด")]
    apply_writes(ward, "2569-10", writes, "A1B2", "ศรี", "swap", "แลกเวร...")
    body = ws.batch_update.call_args[0][0]
    assert body == [{"range": "E2", "values": [[""]]}, {"range": "E3", "values": [["บด"]]}]
    rows = audit.append_rows.call_args[0][0]
    assert len(rows) == 2 and rows[0][1:7] == ["2569-10", "N001", "3", "ด", "", "A1B2"] and rows[0][7] == "ศรี"
    assert all("U" not in r[7] for r in rows)


def test_optimistic_lock():
    ward, ws, _ = _ward([[["ช"]]])  # sheet changed since snapshot
    with pytest.raises(SnapshotMismatch):
        apply_writes(ward, "2569-10", [CellWrite("N001", 3, 2, 5, "ด", "")], "A1B2", "ศรี", "swap", "")
    ws.batch_update.assert_not_called()


def test_dry_run(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    from agent.settings import get_settings

    get_settings.cache_clear()
    ward, ws, audit = _ward([[["ด"]]])
    apply_writes(ward, "2569-10", [CellWrite("N001", 3, 2, 5, "ด", "")], "A1B2", "ศรี", "swap", "")
    ws.batch_update.assert_not_called()
    audit.append_rows.assert_not_called()
