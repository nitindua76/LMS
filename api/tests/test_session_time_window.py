"""
_time_window_ok is the join-window gate independent of audience checks —
tested here with plain namespaces instead of real LiveSession rows since it
only reads status/start_at/end_at/join_before_start_min.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.models.live_session import SessionStatus
from app.routers.employee.sessions import _time_window_ok


def _session(status, start_at, end_at, join_before_start_min=10):
    return SimpleNamespace(
        status=status, start_at=start_at, end_at=end_at,
        join_before_start_min=join_before_start_min,
    )


def test_too_early_before_join_window():
    now = datetime.now(timezone.utc)
    s = _session(SessionStatus.scheduled, now + timedelta(hours=1), now + timedelta(hours=2))
    ok, reason = _time_window_ok(s, now)
    assert not ok
    assert "closer to the start time" in reason


def test_within_join_window_before_start():
    now = datetime.now(timezone.utc)
    s = _session(SessionStatus.scheduled, now + timedelta(minutes=5), now + timedelta(hours=1))
    ok, _ = _time_window_ok(s, now)
    assert ok


def test_scheduled_but_past_end_at_is_rejected():
    now = datetime.now(timezone.utc)
    s = _session(SessionStatus.scheduled, now - timedelta(hours=2), now - timedelta(hours=1))
    ok, reason = _time_window_ok(s, now)
    assert not ok
    assert "ended" in reason


def test_live_session_never_cut_off_by_end_at():
    """A session still marked live past its scheduled end_at (running long)
    must stay joinable — only an explicit admin end or the scheduler's grace
    period closes it, not end_at alone."""
    now = datetime.now(timezone.utc)
    s = _session(SessionStatus.live, now - timedelta(hours=2), now - timedelta(hours=1))
    ok, _ = _time_window_ok(s, now)
    assert ok


def test_ended_session_rejected():
    now = datetime.now(timezone.utc)
    s = _session(SessionStatus.ended, now - timedelta(hours=2), now - timedelta(hours=1))
    ok, reason = _time_window_ok(s, now)
    assert not ok
    assert "ended" in reason


def test_cancelled_session_rejected():
    now = datetime.now(timezone.utc)
    s = _session(SessionStatus.cancelled, now + timedelta(minutes=5), now + timedelta(hours=1))
    ok, reason = _time_window_ok(s, now)
    assert not ok
    assert "cancelled" in reason
