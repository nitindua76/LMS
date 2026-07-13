"""
Server-side per-content-item completion tracking — the anti-spoof layer behind
the video heartbeat and the PDF/embedded-video dwell endpoints.

`SectionProgress.content_done` (bridge.py) is the section-level flag consumed
by the unlock gate and course completion. This module is what native (video/
pdf) content writes into BEFORE that flag is allowed to flip: a section is
only content_done once every native content item in it has an individually
`done` ContentProgress row — not as soon as any single item reports done.
"""
from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.course import ContentType, Section
from app.models.enrollment import ContentProgress, Enrollment

# How much slack (seconds) beyond strict wall-clock elapsed time we allow, to
# absorb client-server clock drift and network latency. Generous enough to
# not annoy real users, tight enough that "one POST claiming 999999 seconds
# watched" gets clamped to something plausible instead of accepted outright.
_GRACE_SECONDS = 15


def _get_or_create(db: Session, enrollment_id: int, content_item_id: int) -> ContentProgress:
    cp = db.query(ContentProgress).filter(
        ContentProgress.enrollment_id == enrollment_id,
        ContentProgress.content_item_id == content_item_id,
    ).first()
    if cp:
        return cp

    cp = ContentProgress(enrollment_id=enrollment_id, content_item_id=content_item_id)
    db.add(cp)
    try:
        db.flush()
    except IntegrityError:
        # Lost a race with a concurrent request for the same (enrollment, item) —
        # e.g. the heartbeat interval and an onPause/onEnded trigger firing back
        # to back. The other request's row already committed; use it instead of
        # failing the request over what is, functionally, a no-op.
        db.rollback()
        cp = db.query(ContentProgress).filter(
            ContentProgress.enrollment_id == enrollment_id,
            ContentProgress.content_item_id == content_item_id,
        ).first()
        if cp is None:
            raise
    return cp


def record_heartbeat(db: Session, enrollment_id: int, content_item_id: int, claimed_watched_seconds: int) -> int:
    """
    Update max_watched_seconds for a video heartbeat, bounded by wall-clock time
    actually elapsed since the last heartbeat (plus grace) — never trusts the
    claimed value outright. Returns the resulting (bounded, monotonic) value.
    """
    cp = _get_or_create(db, enrollment_id, content_item_id)
    now = datetime.now(timezone.utc)
    elapsed = max(0.0, (now - cp.last_heartbeat_at).total_seconds())

    bounded_claim = min(max(0, claimed_watched_seconds), cp.max_watched_seconds + elapsed + _GRACE_SECONDS)
    cp.max_watched_seconds = max(cp.max_watched_seconds, int(bounded_claim))
    cp.last_heartbeat_at = now
    db.flush()
    return cp.max_watched_seconds


def record_dwell(db: Session, enrollment_id: int, content_item_id: int, claimed_dwell_seconds: int) -> int:
    """
    Same bounding as record_heartbeat, but relative to first_seen_at — dwell
    endpoints (PDF mark-read, video mark-watched) are single-shot claims rather
    than repeated heartbeats, so the relevant wall-clock anchor is "when did
    this employee first open this content item," not "since the last call."
    """
    cp = _get_or_create(db, enrollment_id, content_item_id)
    now = datetime.now(timezone.utc)
    elapsed = max(0.0, (now - cp.first_seen_at).total_seconds())

    bounded_claim = min(max(0, claimed_dwell_seconds), elapsed + _GRACE_SECONDS)
    cp.max_watched_seconds = max(cp.max_watched_seconds, int(bounded_claim))
    cp.last_heartbeat_at = now
    db.flush()
    return cp.max_watched_seconds


def mark_done(db: Session, enrollment_id: int, content_item_id: int) -> None:
    cp = _get_or_create(db, enrollment_id, content_item_id)
    if not cp.done:
        cp.done = True
        cp.completed_at = datetime.now(timezone.utc)
        db.flush()


def sync_meeting_attendance(db: Session, live_session, user_id: int) -> None:
    """
    Meeting content items complete on cumulative attended duration rather
    than a client-reported watch time: sums every LiveSessionParticipant row
    (across rejoins) for this user+session and marks the item done once that
    reaches SESSION_ATTENDANCE_COMPLETION_PCT of the session's scheduled
    duration. Call this whenever an attendance row closes — from the LiveKit
    webhook adapter (participant_left / room_finished) and from the
    scheduler when a session is auto-ended.
    """
    from app.models.live_session import LiveSessionParticipant

    content_item = live_session.content_item
    course_id = content_item.section.course_id
    enrollment = db.query(Enrollment).filter(
        Enrollment.user_id == user_id, Enrollment.course_id == course_id,
    ).first()
    if not enrollment:
        return

    total_attended = db.query(
        func.coalesce(func.sum(LiveSessionParticipant.duration_sec), 0)
    ).filter(
        LiveSessionParticipant.live_session_id == live_session.id,
        LiveSessionParticipant.user_id == user_id,
    ).scalar()

    scheduled_duration = max(1, int((live_session.end_at - live_session.start_at).total_seconds()))
    attended_pct = (total_attended / scheduled_duration) * 100
    if attended_pct >= settings.SESSION_ATTENDANCE_COMPLETION_PCT:
        mark_done(db, enrollment.id, content_item.id)


def reset(db: Session, enrollment_id: int, section: Section) -> None:
    """Clear all per-item progress for this section (admin retry/reset path)."""
    item_ids = [ci.id for ci in section.content_items]
    if not item_ids:
        return
    db.query(ContentProgress).filter(
        ContentProgress.enrollment_id == enrollment_id,
        ContentProgress.content_item_id.in_(item_ids),
    ).delete(synchronize_session=False)
    db.flush()


def get_progress_map(db: Session, enrollment_id: int, content_item_ids: list[int]) -> Dict[int, ContentProgress]:
    """Batch-fetch ContentProgress rows for a set of content items, keyed by content_item_id."""
    if not content_item_ids:
        return {}
    rows = db.query(ContentProgress).filter(
        ContentProgress.enrollment_id == enrollment_id,
        ContentProgress.content_item_id.in_(content_item_ids),
    ).all()
    return {row.content_item_id: row for row in rows}


def compute_section_native_pct(
    section: Section, progress_map: Dict[int, ContentProgress]
) -> Optional[float]:
    """
    Average % watched across this section's video items with a known duration
    — the native-content equivalent of the SCORM progress_measure/score_scaled
    average already computed for SCORM sections. Returns None when there's no
    video item to measure (PDF-only or duration-unknown sections), so callers
    can tell "no data" apart from "0% watched."
    """
    video_items = [
        ci for ci in section.content_items
        if ci.type == ContentType.video and ci.video_duration_sec and ci.video_duration_sec > 0
    ]
    if not video_items:
        return None

    fractions = []
    for ci in video_items:
        cp = progress_map.get(ci.id)
        watched = cp.max_watched_seconds if cp else 0
        fractions.append(min(1.0, watched / ci.video_duration_sec))

    return round(sum(fractions) / len(fractions) * 100, 1)


def all_native_items_done(db: Session, enrollment: Enrollment, section: Section) -> bool:
    """
    True once every video/pdf content item in `section` has a `done`
    ContentProgress row for this enrollment. A section with a single content
    item behaves exactly as before; a section with several native items now
    requires all of them, matching how multi-SCO SCORM manifests are already
    gated in bridge.py.
    """
    native_items = [
        ci for ci in section.content_items
        if ci.type in (ContentType.video, ContentType.pdf, ContentType.meeting)
    ]
    if not native_items:
        return True

    done_ids = {
        row.content_item_id
        for row in db.query(ContentProgress.content_item_id).filter(
            ContentProgress.enrollment_id == enrollment.id,
            ContentProgress.content_item_id.in_([ci.id for ci in native_items]),
            ContentProgress.done.is_(True),
        ).all()
    }
    return all(ci.id in done_ids for ci in native_items)
