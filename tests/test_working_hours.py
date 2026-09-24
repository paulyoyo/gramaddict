"""The first session ignores the working hours; later ones follow them."""
from datetime import datetime, timedelta

from GramAddict.core.session_state import SessionState


def _hours_not_now():
    """A one-minute window two hours from now, so now is outside it."""
    start = datetime.now() + timedelta(hours=2)
    end = start + timedelta(minutes=1)
    return [f"{start:%H.%M}-{end:%H.%M}"]


def test_first_session_runs_outside_working_hours(monkeypatch):
    monkeypatch.setattr(SessionState, "ignore_working_hours", True)
    assert SessionState.inside_working_hours(_hours_not_now(), 0) == (True, 0)


def test_later_sessions_wait_for_working_hours(monkeypatch):
    monkeypatch.setattr(SessionState, "ignore_working_hours", False)
    inside, time_left = SessionState.inside_working_hours(_hours_not_now(), 0)
    assert inside is False
    assert timedelta(hours=1) < time_left <= timedelta(hours=2)
