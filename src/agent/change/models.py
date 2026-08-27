from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

State = Literal["PENDING_CLARIFICATION", "PENDING_CONFIRM", "APPLIED", "REJECTED", "CANCELLED", "EXPIRED"]
TERMINAL = {"APPLIED", "REJECTED", "CANCELLED", "EXPIRED"}
OPEN = {"PENDING_CLARIFICATION", "PENDING_CONFIRM"}

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_id() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(4))


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ChangeRequest(Base):
    __tablename__ = "change_requests"

    id: Mapped[str] = mapped_column(String(8), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(8))  # swap | edit
    group_id: Mapped[str] = mapped_column(String(64), index=True)
    month: Mapped[str] = mapped_column(String(7))
    reporter_line_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    reporter_display_name: Mapped[str] = mapped_column(String(200), default="")

    a_staff_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    a_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    a_shift: Mapped[str | None] = mapped_column(String(32), nullable=True)
    b_staff_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    b_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    b_shift: Mapped[str | None] = mapped_column(String(32), nullable=True)
    swap_type: Mapped[str | None] = mapped_column(String(10), nullable=True)  # exchange | give

    target_staff_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    target_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    old_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(64), nullable=True)

    state: Mapped[str] = mapped_column(String(24), default="PENDING_CLARIFICATION", index=True)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    llm_extraction: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    check_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    clarify_rounds: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: utcnow() + timedelta(hours=2))

    def __init__(self, **kw):
        kw.setdefault("id", new_id())
        kw.setdefault("state", "PENDING_CLARIFICATION")
        kw.setdefault("clarify_rounds", 0)
        kw.setdefault("reporter_display_name", "")
        kw.setdefault("raw_text", "")
        now = utcnow()
        kw.setdefault("created_at", now)
        kw.setdefault("updated_at", now)
        kw.setdefault("expires_at", now + timedelta(hours=2))
        super().__init__(**kw)

    @property
    def is_open(self) -> bool:
        return self.state in OPEN

    def touch_expiry(self, hours: float) -> None:
        self.expires_at = utcnow() + timedelta(hours=hours)
