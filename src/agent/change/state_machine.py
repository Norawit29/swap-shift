"""Single place for ChangeRequest transitions (PLAN §5)."""
from __future__ import annotations

from .models import OPEN, TERMINAL, ChangeRequest, utcnow

_ALLOWED: dict[str, set[str]] = {
    "PENDING_CLARIFICATION": {"PENDING_CLARIFICATION", "PENDING_CONFIRM", "REJECTED", "CANCELLED", "EXPIRED"},
    "PENDING_CONFIRM": {"APPLIED", "REJECTED", "CANCELLED", "EXPIRED"},
}


class IllegalTransition(Exception):
    pass


def transition(cr: ChangeRequest, new_state: str) -> ChangeRequest:
    if cr.state in TERMINAL or new_state not in _ALLOWED.get(cr.state, set()):
        raise IllegalTransition(f"{cr.id}: {cr.state} → {new_state}")
    cr.state = new_state
    cr.updated_at = utcnow()
    if new_state in TERMINAL:
        cr.reporter_line_id = None  # data minimization
    return cr


def can_confirm(cr: ChangeRequest, user_id: str) -> bool:
    """Only the reporter, only while PENDING_CONFIRM and not expired. Server-side check."""
    return (cr.state == "PENDING_CONFIRM" and cr.reporter_line_id is not None
            and cr.reporter_line_id == user_id and cr.expires_at > utcnow())


def is_expired(cr: ChangeRequest) -> bool:
    return cr.state in OPEN and cr.expires_at <= utcnow()
