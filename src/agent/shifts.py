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
    return ShiftCodes(tuple(codes), labels, syn, str(off.get("label", "หยุด")))


_STRIP_RE = re.compile(r"\s+")
