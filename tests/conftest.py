import csv
from pathlib import Path

import pytest

from agent.change.name_resolver import Staff
from agent.sheets.reader import parse_roster
from agent.shifts import load_shifts
from agent.thai_date import Month

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    from agent import db as dbm
    from agent.settings import get_settings

    get_settings.cache_clear()
    dbm._engine = None
    dbm._Session = None
    yield
    get_settings.cache_clear()


@pytest.fixture
def codes():
    return load_shifts()


@pytest.fixture
def month():
    return Month(2569, 10)


@pytest.fixture
def roster_values():
    with open(FIX / "roster_2569-10.csv", encoding="utf-8", newline="") as f:
        return [row for row in csv.reader(f)]


@pytest.fixture
def roster(roster_values, month):
    return parse_roster(roster_values, month)


@pytest.fixture
def staff():
    return [Staff("N001", "สมศรี ใจดี", ("ศรี", "พี่ศรี")), Staff("N002", "บุษบา แสงทอง", ("บี", "น้องบี")),
            Staff("N003", "กมล รักงาน", ("กมล",)), Staff("N004", "ศรีวรรณ ดีงาม", ("อ้อ",)),
            Staff("N009", "คนเก่า ลาออก", ("เก่า",), active=False)]
