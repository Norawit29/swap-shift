from datetime import timedelta

import pytest

from agent.change.models import ChangeRequest, utcnow
from agent.change.state_machine import IllegalTransition, can_confirm, is_expired, transition


def _cr(state="PENDING_CONFIRM"):
    return ChangeRequest(id="A1B2", kind="swap", group_id="C1", month="2569-10", reporter_line_id="U1",
                         state=state, expires_at=utcnow() + timedelta(hours=1))


def test_happy_path_clears_reporter_id():
    cr = transition(_cr("PENDING_CLARIFICATION"), "PENDING_CONFIRM")
    assert cr.reporter_line_id == "U1"
    transition(cr, "APPLIED")
    assert cr.state == "APPLIED" and cr.reporter_line_id is None


@pytest.mark.parametrize("frm,to", [("APPLIED", "CANCELLED"), ("PENDING_CONFIRM", "PENDING_CLARIFICATION"),
                                    ("REJECTED", "APPLIED"), ("PENDING_CLARIFICATION", "APPLIED")])
def test_illegal(frm, to):
    with pytest.raises(IllegalTransition):
        transition(_cr(frm), to)


def test_only_reporter_can_confirm():
    cr = _cr()
    assert can_confirm(cr, "U1") and not can_confirm(cr, "U2")
    cr.expires_at = utcnow() - timedelta(seconds=1)
    assert not can_confirm(cr, "U1") and is_expired(cr)
    transition(cr, "EXPIRED")
    assert not can_confirm(cr, "U1")
