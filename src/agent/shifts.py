"""Shift code config (config/shifts.yaml) + roster cell parsing."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from .settings import ROOT


class CellParseError(ValueError):
    pass


@dataclass(frozen=True)
class ShiftCodes:
    codes: tuple[str, ...]
    labels: dict[str, str]
    synonyms: dict[str, str]  # synonym (lower) → code; "" for off
    off_label: str
    grid_rows: dict[str, str] = None  # normalized row label → code (grid layout)
    grid_date_label: str = "วันที่"

    def label(self, code: str) -> str:
        return self.off_label if code == "" else self.labels.get(code, code)

    def is_valid(self, code: str) -> bool:
        return code in self.codes

    def from_text(self, text: str | None) -> str | None:
        """'เช้า'/'ช'/'morning' → 'ช'; off words → ''; unknown → None"""
        if text is None:
            return None
        t = text.strip().lower()
        if t == "":
            return ""
        if t in self.codes:
            return t
        return self.synonyms.get(t)

    def from_words(self, text: str | None) -> list[str] | None:
        """Thai/English shift words run together → codes: 'เช้าบ่าย' → ['ช','บ'], 'บ่ายดึก' → ['บ','ด'],
        'เช้า บ่าย และ ดึก' → ['ช','บ','ด'], 'ชบ' → ['ช','บ'], 'ทั้งวัน' → ['all']. None if unparseable."""
        if text is None:
            return None
        t = re.sub(r"[\s,/+]+|และ|กับ|เวร", "", str(text).strip().lower())
        if not t:
            return None
        if t in ("all", "ทั้งวัน", "ทุกเวร", "เวรทั้งหมด", "ทั้งหมด", "*"):
            return ["all"]
        keys = sorted((k for k in self.synonyms if k), key=len, reverse=True)
        out: list[str] = []
        i = 0
        while i < len(t):
            for k in keys:
                if t.startswith(k, i):
                    code = self.synonyms[k]
                    if code and code not in out:
                        out.append(code)
                    i += len(k)
                    break
            else:
                return None
        return out or None

    def parse_cell(self, cell: str) -> list[str]:
        """'ชบ' → ['ช','บ']; 'ช,conference' → ['ช','conference']; '' → []. Unknown token → CellParseError."""
        s = (cell or "").strip()
        out: list[str] = []
        i = 0
        longest = sorted(self.codes, key=len, reverse=True)
        while i < len(s):
            ch = s[i]
            if ch in " ,/;+|":
                i += 1
                continue
            for code in longest:
                if s.startswith(code, i):
                    out.append(code)
                    i += len(code)
                    break
            else:
                raise CellParseError(f"unknown shift code in cell {cell!r} at {s[i:]!r}")
        return out

    def serialize(self, codes: list[str]) -> str:
        if not codes:
            return ""
        if all(len(c) == 1 for c in codes):
            return "".join(codes)
        return ",".join(codes)


@lru_cache
def load_shifts(path: Path | None = None) -> ShiftCodes:
    p = path or ROOT / "config" / "shifts.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    codes, labels, syn = [], {}, {}
    for item in data["shifts"]:
        code = str(item["code"])
        codes.append(code)
        labels[code] = str(item.get("label", code))
        for s in item.get("synonyms", []):
            syn[str(s).lower()] = code
        syn[code.lower()] = code
    off = data.get("off_shift", {})
    for s in off.get("synonyms", []):
        syn[str(s).lower()] = ""
    grid_rows = {norm_label(k): str(v) for k, v in (data.get("grid_rows") or {}).items()}
    return ShiftCodes(tuple(codes), labels, syn, str(off.get("label", "หยุด")), grid_rows,
                      str(data.get("grid_date_label", "วันที่")))


def norm_label(s: str) -> str:
    return re.sub(r"[\s*:]+", "", str(s or "")).lower()

