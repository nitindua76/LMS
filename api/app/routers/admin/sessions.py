import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.dependencies import require_admin, verify_csrf, get_conferencing_client
from app.conferencing import ConferencingClient
from app.models.user import User
from app.models.course import ContentItem, ContentType
from app.models.live_session import LiveSession, SessionAudienceRule, SessionStatus, LiveSessionParticipant
from app.models.discipline import Discipline
from app.models.level import Level
from app.schemas.live_session import (
    LiveSessionCreate, LiveSessionUpdate, LiveSessionRead,
    SessionAudienceRuleCreate, SessionAudienceRuleRead,
    ParticipantRead,
)
from app.services.audit import audit

router = APIRouter(
    prefix="/admin/courses/{course_id}/sections/{section_id}/content/{item_id}/session",
    tags=["admin-sessions"],
)


def _get_meeting_item(db: Session, course_id: int, section_id: int, item_id: int) -> ContentItem:
    item = (
        db.query(ContentItem)
        .join(ContentItem.section)
        .filter(
            ContentItem.id == item_id,
            ContentItem.section_id == section_id,
        )
        .first()
    )
    if not item or item.section.course_id != course_id:
        raise HTTPException(status_code=404, detail="Content item not found")
    if item.type != ContentType.meeting:
        raise HTTPException(status_code=422, detail="This content item is not a meeting")
    return item


def _get_session(db: Session, item: ContentItem) -> LiveSession:
    """
    A content item can have several LiveSession rows over time (one per
    scheduled occurrence — see models/live_session.py); this always
    resolves to the most recent one. Older rows aren't deleted — they stay
    as attendance/audit history for whoever attended that past occurrence.
    """
    session = (
        db.query(LiveSession)
        .options(joinedload(LiveSession.audience_rules))
        .filter(LiveSession.content_item_id == item.id)
        .order_by(LiveSession.id.desc())
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="No session scheduled for this content item yet")
    return session


@router.get("", response_model=LiveSessionRead)
def get_session(
    course_id: int, section_id: int, item_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    item = _get_meeting_item(db, course_id, section_id, item_id)
    return _get_session(db, item)


@router.post("", response_model=LiveSessionRead, status_code=201, dependencies=[Depends(verify_csrf)])
def create_session(
    course_id: int, section_id: int, item_id: int,
    body: LiveSessionCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    item = _get_meeting_item(db, course_id, section_id, item_id)
    existing = (
        db.query(LiveSession)
        .filter(LiveSession.content_item_id == item.id)
        .order_by(LiveSession.id.desc())
        .first()
    )
    if existing and existing.status in (SessionStatus.scheduled, SessionStatus.live):
        raise HTTPException(
            status_code=409,
            detail=f"A session is already {existing.status.value} for this content item "
                   "— cancel or end it before scheduling a new one",
        )

    room_name = f"lms-c{course_id}-s{section_id}-i{item_id}-{uuid.uuid4().hex[:8]}"
    session = LiveSession(
        content_item_id=item.id,
        room_name=room_name,
        **body.model_dump(),
    )
    db.add(session)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A session already exists for this content item")

    audit(db, actor_id=actor.id, action="create_live_session", target_type="live_session",
          target_id=session.id, detail={"content_item_id": item.id, "room_name": room_name})
    db.commit()
    db.refresh(session)
    return session


@router.put("", response_model=LiveSessionRead, dependencies=[Depends(verify_csrf)])
def update_session(
    course_id: int, section_id: int, item_id: int,
    body: LiveSessionUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    item = _get_meeting_item(db, course_id, section_id, item_id)
    session = _get_session(db, item)
    if session.status in (SessionStatus.live, SessionStatus.ended):
        raise HTTPException(status_code=422, detail=f"Cannot edit a session that is already {session.status.value}")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(session, field, value)
    if session.end_at <= session.start_at:
        db.rollback()
        raise HTTPException(status_code=422, detail="end_at must be after start_at")
    db.flush()
    audit(db, actor_id=actor.id, action="update_live_session", target_type="live_session", target_id=session.id)
    db.commit()
    db.refresh(session)
    return session


@router.post("/cancel", response_model=LiveSessionRead, dependencies=[Depends(verify_csrf)])
def cancel_session(
    course_id: int, section_id: int, item_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    item = _get_meeting_item(db, course_id, section_id, item_id)
    session = _get_session(db, item)
    if session.status == SessionStatus.ended:
        raise HTTPException(status_code=422, detail="Cannot cancel a session that already ended")
    session.status = SessionStatus.cancelled
    db.flush()
    audit(db, actor_id=actor.id, action="cancel_live_session", target_type="live_session", target_id=session.id)
    db.commit()
    db.refresh(session)
    return session


@router.post("/end", response_model=LiveSessionRead, dependencies=[Depends(verify_csrf)])
async def end_session(
    course_id: int, section_id: int, item_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
    conferencing: ConferencingClient = Depends(get_conferencing_client),
):
    item = _get_meeting_item(db, course_id, section_id, item_id)
    session = _get_session(db, item)
    if session.status not in (SessionStatus.scheduled, SessionStatus.live):
        raise HTTPException(status_code=422, detail=f"Cannot end a session that is {session.status.value}")

    try:
        await conferencing.end_room(session.room_name)
    except Exception:
        pass  # room may not exist yet (nobody joined) — still mark the session ended below

    session.status = SessionStatus.ended
    db.flush()
    audit(db, actor_id=actor.id, action="end_live_session", target_type="live_session", target_id=session.id)
    db.commit()
    db.refresh(session)
    return session


@router.get("/participants", response_model=List[ParticipantRead])
def list_participants(
    course_id: int, section_id: int, item_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    item = _get_meeting_item(db, course_id, section_id, item_id)
    session = _get_session(db, item)
    return (
        db.query(LiveSessionParticipant)
        .filter(LiveSessionParticipant.live_session_id == session.id)
        .order_by(LiveSessionParticipant.joined_at)
        .all()
    )


# ── Audience rules ───────────────────────────────────────────────────────────

@router.get("/audience", response_model=List[SessionAudienceRuleRead])
def list_audience_rules(
    course_id: int, section_id: int, item_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    item = _get_meeting_item(db, course_id, section_id, item_id)
    session = _get_session(db, item)
    return session.audience_rules


@router.post("/audience", response_model=SessionAudienceRuleRead, status_code=201,
             dependencies=[Depends(verify_csrf)])
def add_audience_rule(
    course_id: int, section_id: int, item_id: int,
    body: SessionAudienceRuleCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    item = _get_meeting_item(db, course_id, section_id, item_id)
    session = _get_session(db, item)

    if body.discipline_id is not None and not db.get(Discipline, body.discipline_id):
        raise HTTPException(status_code=422, detail="Discipline not found")
    if body.level_id is not None and not db.get(Level, body.level_id):
        raise HTTPException(status_code=422, detail="Level not found")
    if body.user_id is not None and not db.get(User, body.user_id):
        raise HTTPException(status_code=422, detail="User not found")

    rule = SessionAudienceRule(
        live_session_id=session.id,
        discipline_id=body.discipline_id,
        level_id=body.level_id,
        user_id=body.user_id,
    )
    db.add(rule)
    db.flush()
    audit(db, actor_id=actor.id, action="add_session_audience_rule", target_type="session_audience_rule",
          target_id=rule.id, detail={"live_session_id": session.id})
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/audience/{rule_id}", status_code=204, dependencies=[Depends(verify_csrf)])
def remove_audience_rule(
    course_id: int, section_id: int, item_id: int, rule_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    item = _get_meeting_item(db, course_id, section_id, item_id)
    session = _get_session(db, item)
    rule = db.query(SessionAudienceRule).filter(
        SessionAudienceRule.id == rule_id,
        SessionAudienceRule.live_session_id == session.id,
    ).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Audience rule not found")
    db.delete(rule)
    audit(db, actor_id=actor.id, action="remove_session_audience_rule", target_type="session_audience_rule",
          target_id=rule_id, detail={"live_session_id": session.id})
    db.commit()
