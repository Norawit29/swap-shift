"""Postback data: action=confirm&id=A1B2 / action=cancel&id=A1B2. Free-text fallback: ยืนยัน / ยกเลิก."""
from __future__ import annotations

import re
from urllib.parse import parse_qs

CONFIRM_WORDS = {"ยืนยัน", "ยืนยันค่ะ", "ยืนยันครับ", "ok", "โอเค", "ใช่", "ใช่ค่ะ", "ใช่ครับ", "ถูกต้อง", "ตกลง"}
CANCEL_WORDS = {"ยกเลิก", "ยกเลิกค่ะ", "ยกเลิกครับ", "ไม่ใช่", "ไม่", "ผิด", "cancel"}
_ID_RE = re.compile(r"#?([A-Z0-9]{4})\b")


def confirm_data(cid: str) -> str:
    return f"action=confirm&id={cid}"


def cancel_data(cid: str) -> str:
    return f"action=cancel&id={cid}"


def parse_postback(data: str) -> tuple[str | None, str | None]:
    q = parse_qs(data or "")
    return (q.get("action", [None])[0], q.get("id", [None])[0])


def parse_free_text(text: str) -> tuple[str | None, str | None]:
    """→ ('confirm'|'cancel'|None, id|None)"""
    t = text.strip().lower().rstrip("ๆ!.")
    words = re.sub(r"[^\wก-๙ ]", " ", t).split()
    m = _ID_RE.search(text.upper())
    cid = m.group(1) if m else None
    core = " ".join(w for w in words if not _ID_RE.fullmatch(w.upper()))
    if core in CONFIRM_WORDS or any(core.startswith(w) for w in ("ยืนยัน", "ok", "โอเค", "ใช่")):
        return "confirm", cid
    if core in CANCEL_WORDS or core.startswith("ยกเลิก") or core.startswith("ไม่ใช่"):
        return "cancel", cid
    return None, cid
