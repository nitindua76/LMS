"""
Employee-facing live session endpoints: eligibility/countdown + join/leave,
plus host-side participant management (add/remove someone from the session's
audience mid-session — see the "Participants" section below).

Join is the security boundary for the whole conferencing feature — it always
re-validates enrollment, audience membership, and the time window against
live DB state before minting a LiveKit token; nothing here trusts a
client-supplied room name or role.
"""
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import require_employee, get_current_user, verify_csrf, get_conferencing_client
from app.conferencing import ConferencingClient, ParticipantPermissions
from app.models.user import User
from app.models.course import Course, ContentItem, ContentType, Section
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.live_session import (
    LiveSession, SessionMode, SessionStatus, SessionAudienceRule, LiveSessionParticipant,
)
from app.schemas.live_session import (
    JoinEligibility, JoinResponse, LiveSessionRead,
    SessionParticipantAddByUser, SessionParticipantAddByCpf, SessionParticipantRead,
)
from app.services import content_progress
from app.services import mail_api
from app.services.session_audience import is_user_in_session_audience
from app.services.live_session_identity import make_identity, parse_identity
from app.services.provisioning import get_or_provision_by_cpf
from app.services.sso import get_employee_api_client
from app.services.audit import audit
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
    return timedelta(minutes=n)


# ── Host-side participant management ─────────────────────────────────────────
# Lets whoever is hosting a live session (host_user_id — set when the
# session was scheduled, and can be EITHER role: LiveSessionCreate.host_user_id
# has no role restriction, same as Instant Rooms' owner) add someone who
# isn't normally in this course's audience, or remove/kick someone
# currently in the room — without needing to go edit the course's audience
# rules mid-call. Reuses the SAME SessionAudienceRule mechanism the admin
# "Additional audience for this session" panel already writes to
# (MeetingSessionPanel.tsx/admin/sessions.py) — one underlying model, two
# UIs (admin pre-session planning, host in-the-moment).
#
# Deliberately gated on get_current_user, NOT require_employee — an admin
# can be a session's host too, and require_employee would 403 them out of
# managing their own session (this bug was caught by an end-to-end test
# against the real endpoint, not just code review).

def _load_session_as_host(db: Session, live_session_id: int, user: User) -> LiveSession:
    live_session = (
        db.query(LiveSession)
        .options(joinedload(LiveSession.audience_rules), joinedload(LiveSession.content_item))
        .filter(LiveSession.id == live_session_id)
        .first()
    )
    if not live_session:
        raise HTTPException(status_code=404, detail="Session not found")
    if live_session.host_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only this session's host can manage participants")
    return live_session


def _ensure_enrolled(db: Session, target: User, course: Course) -> Enrollment:
    """Host-added participants must not have to separately self-enroll —
    mirrors employee/courses.py's start_course exactly (same default
    status/deadline logic), just triggered by the host instead of the
    person themselves."""
    existing = db.query(Enrollment).filter(
        Enrollment.user_id == target.id, Enrollment.course_id == course.id,
    ).first()
    if existing:
        return existing
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(days=course.duration_days) if course.duration_days else None
    enrollment = Enrollment(
        user_id=target.id, course_id=course.id,
        status=EnrollmentStatus.in_progress, started_at=now, deadline_at=deadline,
    )
    db.add(enrollment)
    db.flush()
    return enrollment


def _session_participants_read(db: Session, live_session: LiveSession) -> List[SessionParticipantRead]:
    open_user_ids = {
        r.user_id for r in db.query(LiveSessionParticipant).filter(
            LiveSessionParticipant.live_session_id == live_session.id,
            LiveSessionParticipant.left_at.is_(None),
        ).all()
    }
    rules = [r for r in live_session.audience_rules if r.user_id is not None]
    out = []
    for r in rules:
        target = db.get(User, r.user_id)
        if not target:
            continue
        out.append(SessionParticipantRead(
            rule_id=r.id, user_id=target.id, name=target.name, email=target.email,
            currently_in_room=target.id in open_user_ids,
        ))
    return out


@router.get(
    "/sessions/{live_session_id}/participants",
    response_model=List[SessionParticipantRead],
)
def list_session_participants(
    live_session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Host-only: everyone individually added to this session's audience
    (not the whole department/level audience — same distinction
    admin/courses.py's target-users list draws from CourseTarget)."""
    live_session = _load_session_as_host(db, live_session_id, user)
    return _session_participants_read(db, live_session)


def _add_session_participant(db: Session, live_session: LiveSession, target: User, actor: User) -> SessionParticipantRead:
    course = live_session.content_item.section.course
    existing_rule = db.query(SessionAudienceRule).filter(
        SessionAudienceRule.live_session_id == live_session.id,
        SessionAudienceRule.user_id == target.id,
    ).first()
    if not existing_rule:
        rule = SessionAudienceRule(live_session_id=live_session.id, user_id=target.id)
        db.add(rule)
        db.flush()
        audit(db, actor_id=actor.id, action="host_add_session_participant", target_type="live_session",
              target_id=live_session.id, detail={"user_id": target.id})
    else:
        rule = existing_rule

    _ensure_enrolled(db, target, course)
    db.commit()

    # Best-effort invite email — points at the course page, not a direct
    # LiveKit link, since actually joining still goes through the normal
    # eligibility/join flow (time window, etc.) — see join_session above.
    try:
        base = settings.FRONTEND_URL.rstrip("/")
        mail_api.send_meeting_link_email(
            db, to_email=target.email, link=f"{base}/my/courses/{course.id}", room_name=course.title,
        )
    except Exception:
        pass

    open_user_ids = {
        r.user_id for r in db.query(LiveSessionParticipant).filter(
            LiveSessionParticipant.live_session_id == live_session.id,
            LiveSessionParticipant.left_at.is_(None),
        ).all()
    }
    return SessionParticipantRead(
        rule_id=rule.id, user_id=target.id, name=target.name, email=target.email,
        currently_in_room=target.id in open_user_ids,
    )


@router.post(
    "/sessions/{live_session_id}/participants",
    response_model=SessionParticipantRead, status_code=201,
    dependencies=[Depends(verify_csrf)],
)
def add_session_participant_by_user(
    live_session_id: int,
    body: SessionParticipantAddByUser,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    live_session = _load_session_as_host(db, live_session_id, user)
    target = db.get(User, body.user_id)
    if not target:
        raise HTTPException(status_code=422, detail="User not found")
    return _add_session_participant(db, live_session, target, user)


@router.post(
    "/sessions/{live_session_id}/participants/by-cpf",
    response_model=SessionParticipantRead, status_code=201,
    dependencies=[Depends(verify_csrf)],
)
def add_session_participant_by_cpf(
    live_session_id: int,
    body: SessionParticipantAddByCpf,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Same auto-provisioning as Instant Rooms' CPF-add (see
    services/provisioning.py) — works even for someone who has never
    logged in yet."""
    live_session = _load_session_as_host(db, live_session_id, user)
    target = get_or_provision_by_cpf(db, body.cpf, employee_client=get_employee_api_client(db))
    return _add_session_participant(db, live_session, target, user)


@router.delete(
    "/sessions/{live_session_id}/participants/{target_user_id}",
    status_code=204,
    dependencies=[Depends(verify_csrf)],
)
async def remove_session_participant(
    live_session_id: int,
    target_user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    conferencing: ConferencingClient = Depends(get_conferencing_client),
):
    """
    Removes an ad-hoc invite (deletes the SessionAudienceRule the host
    added, if any) AND kicks them out of the live room right now if
    they're currently connected. Deliberately does NOT touch course-level
    enrollment or department/level targeting — someone who's in this
    session's audience because their department is normally targeted at
    this course stays eligible to rejoin later; this only undoes what the
    host themselves granted/can revoke on the spot.
    """
    live_session = _load_session_as_host(db, live_session_id, user)

    rule = db.query(SessionAudienceRule).filter(
        SessionAudienceRule.live_session_id == live_session.id,
        SessionAudienceRule.user_id == target_user_id,
    ).first()
    if rule:
        db.delete(rule)

    identity = make_identity(target_user_id)
    try:
        await conferencing.remove_participant(live_session.room_name, identity)
    except Exception:
        pass  # not currently connected — nothing to kick

    now = datetime.now(timezone.utc)
    open_row = db.query(LiveSessionParticipant).filter(
        LiveSessionParticipant.live_session_id == live_session.id,
        LiveSessionParticipant.user_id == target_user_id,
        LiveSessionParticipant.left_at.is_(None),
    ).first()
    if open_row:
        open_row.left_at = now
        open_row.duration_sec += max(0, int((now - open_row.joined_at).total_seconds()))
        db.flush()
        content_progress.sync_meeting_attendance(db, live_session, target_user_id)

    audit(db, actor_id=user.id, action="host_remove_session_participant", target_type="live_session",
          target_id=live_session.id, detail={"user_id": target_user_id})
    db.commit()
