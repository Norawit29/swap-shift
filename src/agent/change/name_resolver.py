"""Deterministic name → staff resolution.

Order: exact (nickname / full / first name) → unique prefix → fuzzy (typo tolerance, owner request 2026-08-28):
a single candidate with similarity ≥ FUZZY_MIN that leads the runner-up by ≥ FUZZY_GAP is accepted; several close
candidates → ambiguous (caller asks). The reporter always sees the resolved name in the summary before confirming."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

_PREFIX_RE = re.compile(r"^(พี่|น้อง|คุณ|หมอ|นพ\.|พญ\.|นาง|นางสาว|นาย|น\.ส\.)\s*")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class Staff:
    staff_id: str
    full_name: str
    nicknames: tuple[str, ...] = ()
    active: bool = True

    @property
    def display(self) -> str:
        return self.nicknames[0] if self.nicknames else self.full_name.split()[0]


FUZZY_MIN = 0.75
FUZZY_GAP = 0.08


@dataclass
class Resolution:
    query: str
    matches: list[Staff] = field(default_factory=list)
    fuzzy: bool = False  # resolved by similarity (not an exact spelling)

    @property
    def ok(self) -> bool:
        return len(self.matches) == 1

    @property
    def staff(self) -> Staff:
        assert self.ok
        return self.matches[0]

    @property
    def ambiguous(self) -> bool:
        return len(self.matches) > 1


def normalize(name: str) -> str:
    s = _WS_RE.sub(" ", (name or "").strip()).lower()
    prev = None
    while prev != s:
        prev, s = s, _PREFIX_RE.sub("", s)
    return s.replace(" ", "")


def resolve(query: str, staff: list[Staff]) -> Resolution:
    q = normalize(query)
    res = Resolution(query)
    if not q:
        return res
    active = [s for s in staff if s.active]
    # 1) exact nickname / full name / first name
    exact = [s for s in active if q in {normalize(n) for n in (*s.nicknames, s.full_name, s.full_name.split()[0])}]
    if exact:
        res.matches = exact
        return res
    # 2) prefix match on nickname or first name (e.g. 'ศรี' ↔ 'ศรีวรรณ') — only if unique
    pref = [s for s in active if any(normalize(n).startswith(q) or q.startswith(normalize(n))
                                     for n in (*s.nicknames, s.full_name.split()[0]) if normalize(n))]
    if pref:
        res.matches = pref
        return res
    # 3) fuzzy — typo tolerance
    scored: list[tuple[float, Staff]] = []
    for s in active:
        best = max((SequenceMatcher(None, q, normalize(n)).ratio()
                    for n in (*s.nicknames, s.full_name.split()[0]) if normalize(n)), default=0.0)
        if best >= FUZZY_MIN:
            scored.append((best, s))
    scored.sort(key=lambda x: -x[0])
    if scored:
        res.fuzzy = True
        if len(scored) == 1 or scored[0][0] - scored[1][0] >= FUZZY_GAP:
            res.matches = [scored[0][1]]
        else:
            res.matches = [s for _, s in scored[:4]]
    return res
