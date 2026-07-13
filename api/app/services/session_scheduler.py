"""
In-process scheduler (APScheduler) for live sessions — deliberately no new
infra beyond the api container. Every ~30s:
  1. email starting_soon/started reminders (SentSessionReminder dedupes so a
     restart or overlapping tick never double-sends), and
  2. auto-close any session nobody manually ended, well past its scheduled
     end time.

Runs as a single BackgroundScheduler in the api process — fine for a single
uvicorn worker (the dev/current deployment). Running multiple api workers or
replicas in production would double-fire these jobs; that needs a leader
election or a dedicated worker process before scaling out horizontally.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.live_session import (
    LiveSession, LiveSessionParticipant, SessionStatus, SentSessionReminder, SessionReminderType,
)
from app.models.user import User
from app.services import content_progress
from app.services.session_audience import resolve_session_audience_user_ids
from app.services.mailer import send_email

logger = logging.getLogger(__name__)

_REMINDER_LEAD_MINUTES = 15
_END_GRACE_MINUTES = 30  # auto-close a session nobody manually ended, well past its scheduled end


def _run_once() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        _send_reminders(db, now)
        _flip_overdue_to_ended(db, now)
    except Exception:
        logger.exception("session_scheduler tick failed")
    finally:
        db.close()


def _send_reminders(db: Session, now: datetime) -> None:
    starting_soon = (
        db.query(LiveSession)
        .filter(
            LiveSession.status == SessionStatus.scheduled,
            LiveSession.start_at <= now + timedelta(minutes=_REMINDER_LEAD_MINUTES),
            LiveSession.start_at > now,
        )
        .all()
    )
    for session in starting_soon:
        _send_reminder(
            db, session, SessionReminderType.starting_soon,
            subject="Your session is starting soon",
            body_fn=lambda s=session: f"Your session starts at {s.start_at.isoformat()}.",
        )

    live_now = db.query(LiveSession).filter(LiveSession.status == SessionStatus.live).all()
    for session in live_now:
        _send_reminder(
            db, session, SessionReminderType.started,
            subject="Your session has started",
            body_fn=lambda: "Your session is live now — join it from the course.",
        )


def _send_reminder(
    db: Session, session: LiveSession, reminder_type: SessionReminderType,
    subject: str, body_fn: Callable[[], str],
) -> None:
    course_id = session.content_item.section.course_id
    audience_ids = resolve_session_audience_user_ids(db, session, course_id)
    if not audience_ids:
        return

    already_sent = {
        row.user_id
        for row in db.query(SentSessionReminder).filter(
            SentSessionReminder.live_session_id == session.id,
            SentSessionReminder.reminder_type == reminder_type,
        ).all()
    }
    to_notify = audience_ids - already_sent
    if not to_notify:
        return

    for user in db.query(User).filter(User.id.in_(to_notify)).all():
        try:
            send_email(user.email, subject, body_fn())
        except Exception:
            logger.exception("Failed to send session reminder to user %s", user.id)
            continue
        db.add(SentSessionReminder(
            live_session_id=session.id, user_id=user.id, reminder_type=reminder_type,
        ))
    db.commit()


def _flip_overdue_to_ended(db: Session, now: datetime) -> None:
    overdue = (
        db.query(LiveSession)
        .filter(
            LiveSession.status.in_([SessionStatus.scheduled, SessionStatus.live]),
            LiveSession.end_at < now - timedelta(minutes=_END_GRACE_MINUTES),
        )
        .all()
    )
    for session in overdue:
        session.status = SessionStatus.ended
        open_rows = db.query(LiveSessionParticipant).filter(
            LiveSessionParticipant.live_session_id == session.id,
            LiveSessionParticipant.left_at.is_(None),
        ).all()
        for row in open_rows:
            row.left_at = now
            row.duration_sec += max(0, int((now - row.joined_at).total_seconds()))
            db.flush()
            content_progress.sync_meeting_attendance(db, session, row.user_id)
    if overdue:
        db.commit()


_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(_run_once, "interval", seconds=30, id="session_scheduler_tick", max_instances=1)
    _scheduler.start()


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
