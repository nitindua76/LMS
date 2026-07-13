"""
Employee-facing live session endpoints: eligibility/countdown + join/leave.

Join is the security boundary for the whole conferencing feature — it always
re-validates enrollment, audience membership, and the time window against
live DB state before minting a LiveKit token; nothing here trusts a
client-supplied room name or role.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import require_employee, verify_csrf, get_conferencing_client
from app.conferencing import ConferencingClient, ParticipantPermissions
from app.models.user import User
from app.models.course import ContentItem, ContentType, Section
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.live_session import LiveSession, SessionMode, SessionStatus, LiveSessionParticipant
from app.schemas.live_session import JoinEligibility, JoinResponse, LiveSessionRead
from app.services import content_progress
from app.services.session_audience import is_user_in_session_audience
from app.services.live_session_identity import make_identity
from app.config import settings

router = APIRouter(prefix="/my", tags=["employee-sessions"])


def _get_enrollment_and_session(
    enrollment_id: int, section_id: int, item_id: int, user: User, db: Session
) -> tuple[Enrollment, LiveSession]:
    enrollment = db.query(Enrollment).filter(
        Enrollment.id == enrollment_id, Enrollment.user_id == user.id,
    ).first()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    section = db.query(Section).filter(
        Section.id == section_id, Section.course_id == enrollment.course_id,
    ).first()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    item = db.query(ContentItem).filter(
        ContentItem.id == item_id, ContentItem.section_id == section_id,
        ContentItem.type == ContentType.meeting,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Meeting content item not found")

    # Most recent occurrence for this content item — see admin/sessions.py's
    # _get_session for why this can no longer assume exactly one row.
    live_session = (
        db.query(LiveSession)
        .options(joinedload(LiveSession.audience_rules))
        .filter(LiveSession.content_item_id == item.id)
        .order_by(LiveSession.id.desc())
        .first()
    )
    if not live_session:
        raise HTTPException(status_code=404, detail="No session scheduled for this content item yet")

    return enrollment, live_session


def _time_window_ok(live_session: LiveSession, now: datetime) -> tuple[bool, str | None]:
    if live_session.status == SessionStatus.live:
        return True, None  # already running — never cut off by end_at alone; admin ends it explicitly
    if live_session.status == SessionStatus.ended:
        return False, "This session has ended"
    if live_session.status == SessionStatus.cancelled:
        return False, "This session has been cancelled"
    # scheduled
    join_opens_at = live_session.start_at - _minutes(live_session.join_before_start_min)
    if now < join_opens_at:
        return False, "Joining opens closer to the start time"
    if now > live_session.end_at:
        return False, "This session has ended"
    return True, None


def _check_eligibility(
    db: Session, enrollment: Enrollment, live_session: LiveSession, user: User, now: datetime
) -> tuple[bool, str | None]:
    if live_session.status == SessionStatus.cancelled:
        return False, "This session has been cancelled"
    if not is_user_in_session_audience(db, live_session, enrollment.course_id, user):
        return False, "You are not part of this session's audience"
    return _time_window_ok(live_session, now)


@router.get(
    "/enrollments/{enrollment_id}/sections/{section_id}/content/{item_id}/session",
    response_model=JoinEligibility,
)
def session_eligibility(
    enrollment_id: int, section_id: int, item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_employee),
):
    enrollment, live_session = _get_enrollment_and_session(enrollment_id, section_id, item_id, user, db)
    now = datetime.now(timezone.utc)
    eligible, reason = _check_eligibility(db, enrollment, live_session, user, now)

    join_opens_at = live_session.start_at - _minutes(live_session.join_before_start_min)
    seconds_until = int((join_opens_at - now).total_seconds())

    return JoinEligibility(
        eligible=eligible,
        reason=reason,
        session=LiveSessionRead.model_validate(live_session),
        seconds_until_join_opens=max(0, seconds_until),
    )


@router.post(
    "/enrollments/{enrollment_id}/sections/{section_id}/content/{item_id}/session/join",
    response_model=JoinResponse,
    dependencies=[Depends(verify_csrf)],
)
async def join_session(
    enrollment_id: int, section_id: int, item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_employee),
    conferencing: ConferencingClient = Depends(get_conferencing_client),
):
    enrollment, live_session = _get_enrollment_and_session(enrollment_id, section_id, item_id, user, db)
    now = datetime.now(timezone.utc)
    eligible, reason = _check_eligibility(db, enrollment, live_session, user, now)
    if not eligible:
        raise HTTPException(status_code=403, detail=reason)

    is_host = live_session.host_user_id == user.id
    if is_host:
        permissions = ParticipantPermissions(
            can_publish=True, can_subscribe=True, can_publish_data=True, room_admin=True,
        )
        role = "host"
    elif live_session.mode == SessionMode.webinar:
        permissions = ParticipantPermissions(
            can_publish=False, can_subscribe=True, can_publish_data=True,
        )
        role = "attendee"
    else:
        permissions = ParticipantPermissions(
            can_publish=True, can_subscribe=True, can_publish_data=True,
        )
        role = "attendee"

    identity = make_identity(user.id)
    token = conferencing.generate_token(live_session.room_name, identity, user.name, permissions)

    if live_session.status == SessionStatus.scheduled:
        live_session.status = SessionStatus.live
        db.commit()

    return JoinResponse(
        livekit_url=settings.LIVEKIT_URL,
        token=token.token,
        room_name=live_session.room_name,
        identity=identity,
        role=role,
    )


@router.post(
    "/enrollments/{enrollment_id}/sections/{section_id}/content/{item_id}/session/leave",
    status_code=204,
    dependencies=[Depends(verify_csrf)],
)
def leave_session(
    enrollment_id: int, section_id: int, item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_employee),
):
    """
    Best-effort attendance close on explicit leave — the LiveKit webhook
    (participant_left / room_finished) is the authoritative path and will
    also close this row if the client disconnects without calling this.
    """
    _enrollment, live_session = _get_enrollment_and_session(enrollment_id, section_id, item_id, user, db)
    now = datetime.now(timezone.utc)
    open_row = (
        db.query(LiveSessionParticipant)
        .filter(
            LiveSessionParticipant.live_session_id == live_session.id,
            LiveSessionParticipant.user_id == user.id,
            LiveSessionParticipant.left_at.is_(None),
        )
        .first()
    )
    if open_row:
        open_row.left_at = now
        open_row.duration_sec += max(0, int((now - open_row.joined_at).total_seconds()))
        db.flush()
        content_progress.sync_meeting_attendance(db, live_session, user.id)
        db.commit()


def _minutes(n: int):
    from datetime import timedelta
    return timedelta(minutes=n)
