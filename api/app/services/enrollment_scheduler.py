"""
Proactive enrollment-deadline expiry. Without this, an enrollment whose
deadline_at has passed only ever flips to `expired` lazily, the next time
the employee happens to touch content again (see
services/enrollment.py::enrollment_deadline_passed) — meaning "My Courses"
can keep showing a stale `in_progress`/`not_started` for an enrollment
that's actually well past its deadline, for as long as the employee doesn't
click back into it.

Separate in-process APScheduler instance from session_scheduler.py — same
approach (no new infra), but a distinct concern (general enrollment
deadlines vs. live-session scheduling), so they don't get coupled together.
"""
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from app.database import SessionLocal
from app.models.enrollment import Enrollment, EnrollmentStatus

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_SECONDS = 300  # deadlines are day-granularity; no need to poll as often as live-session status


def _run_once() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        lapsed = (
            db.query(Enrollment)
            .filter(
                Enrollment.status.in_([EnrollmentStatus.not_started, EnrollmentStatus.in_progress]),
                Enrollment.deadline_at.isnot(None),
                Enrollment.deadline_at < now,
            )
            .all()
        )
        for enrollment in lapsed:
            enrollment.status = EnrollmentStatus.expired
        if lapsed:
            db.commit()
    except Exception:
        logger.exception("enrollment_scheduler tick failed")
    finally:
        db.close()


_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _run_once, "interval", seconds=_CHECK_INTERVAL_SECONDS,
        id="enrollment_expiry_tick", max_instances=1,
    )
    _scheduler.start()


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
