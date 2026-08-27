"""Thai calendar helpers. Month keys are 'YYYY-MM' in BE year (พ.ศ.), e.g. '2569-10'."""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date

BE_OFFSET = 543

MONTHS_FULL = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
               "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
MONTHS_ABBR = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
_MONTH_ALIASES = {"กรกฏาคม": 7, "มิย": 6, "พย": 11, "กย": 9, "ตค": 10, "สค": 8, "กค": 7, "มค": 1, "กพ": 2,
                  "มีค": 3, "เมย": 4, "พค": 5, "ธค": 12}
_MONTH_RE = re.compile(r"^(\d{4})-(\d{1,2})$")


@dataclass(frozen=True, order=True)
class Month:
    year_be: int
    month: int

    @property
    def key(self) -> str:
        return f"{self.year_be}-{self.month:02d}"

    @property
    def year_ce(self) -> int:
        return self.year_be - BE_OFFSET

    @property
    def days(self) -> int:
        return calendar.monthrange(self.year_ce, self.month)[1]

    @property
    def label(self) -> str:
        return f"{MONTHS_FULL[self.month - 1]} {self.year_be}"

    @property
    def abbr(self) -> str:
        return MONTHS_ABBR[self.month - 1]

    def next(self) -> Month:
        return Month(self.year_be + (1 if self.month == 12 else 0), 1 if self.month == 12 else self.month + 1)

    def contains(self, day: int) -> bool:
        return 1 <= day <= self.days

    @classmethod
    def from_key(cls, key: str) -> Month:
        m = _MONTH_RE.match(key.strip())
        if not m:
            raise ValueError(f"bad month key: {key!r}")
        y, mo = int(m.group(1)), int(m.group(2))
        if not 1 <= mo <= 12:
            raise ValueError(f"bad month key: {key!r}")
        return cls(_to_be(y), mo)

    @classmethod
    def from_date(cls, d: date) -> Month:
        return cls(d.year + BE_OFFSET, d.month)

    def first_date(self) -> date:
        return date(self.year_ce, self.month, 1)


def _to_be(year: int) -> int:
    if year < 100:  # '69' → 2569
        return 2500 + year
    if year < 2400:  # CE
        return year + BE_OFFSET
    return year


def today_be(today: date | None = None) -> tuple[date, int]:
    d = today or date.today()
    return d, d.year + BE_OFFSET


def month_index(text: str) -> int | None:
    """'ต.ค.' / 'ตุลาคม' / 'ตค' / '10' → 10"""
    t = text.strip().replace(" ", "")
    if t.isdigit():
        n = int(t)
        return n if 1 <= n <= 12 else None
    for i, name in enumerate(MONTHS_FULL, 1):
        if t == name:
            return i
    for i, ab in enumerate(MONTHS_ABBR, 1):
        if t == ab or t == ab.replace(".", ""):
            return i
    return _MONTH_ALIASES.get(t.replace(".", ""))


_TOKEN_RE = re.compile(
    r"(?P<key>\d{4}-\d{1,2})|(?P<slash>(\d{1,2})/(\d{2,4}))|(?P<name>[ก-๙.]+)\s*(?P<year>\d{2,4})?"
)


def parse_month(text: str, *, default_year_be: int | None = None, today: date | None = None) -> Month | None:
    """Accepts '2569-10', '10/2569', 'ต.ค.', 'ตุลาคม', 'ต.ค. 69'. Bare month name → default year (this year BE)."""
    text = text.strip()
    if not text:
        return None
    _, ybe = today_be(today)
    default_year_be = default_year_be or ybe
    for m in _TOKEN_RE.finditer(text):
        if m.group("key"):
            try:
                return Month.from_key(m.group("key"))
            except ValueError:
                continue
        if m.group("slash"):
            mo, y = int(m.group(3)), int(m.group(4))
            if 1 <= mo <= 12:
                return Month(_to_be(y), mo)
            continue
        if m.group("name"):
            idx = month_index(m.group("name"))
            if idx:
                y = _to_be(int(m.group("year"))) if m.group("year") else default_year_be
                return Month(y, idx)
    return None


def fmt_day(month: Month, day: int) -> str:
    """3, 2569-10 → '3 ต.ค.'"""
    return f"{day} {month.abbr}"
