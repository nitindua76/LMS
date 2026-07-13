"""
LMS-specific adapter over app/conferencing/webhooks.py: turns generic
participant/room events into updates on LiveSession / LiveSessionParticipant.
Everything here is deliberately outside the app/conferencing boundary — it's
the one place that knows both about LiveKit event shapes and LMS tables.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.conferencing import verify_and_parse_webhook
from app.models.live_session import LiveSession, LiveSessionParticipant, SessionStatus
from app.services import content_progress
from app.services.live_session_identity import parse_identity

router = APIRouter(prefix="/webhooks/livekit", tags=["webhooks"])


@router.post("", status_code=204)
async def livekit_webhook(
    request: Request,
    authorization: str = Header(...),
    db: Session = Depends(get_db),
):
    body = await request.body()
    try:
        event = verify_and_parse_webhook(
            body, authorization, settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    if event is None:
        return  # event type we don't model — nothing to do

    session = db.query(LiveSession).filter(LiveSession.room_name == event.room_name).first()
    if not session:
        return  # room not tied to a scheduled session (or already cleaned up) — ignore

    now = datetime.now(timezone.utc)

    if event.event == "room_started":
        if session.status == SessionStatus.scheduled:
            session.status = SessionStatus.live
        db.commit()
        return

    if event.event == "room_finished":
        if session.status in (SessionStatus.scheduled, SessionStatus.live):
            session.status = SessionStatus.ended
        _close_dangling_participants(db, session, now)
        db.commit()
        return

    if event.participant is None:
        return
    user_id = parse_identity(event.participant.identity)
    if user_id is None:
        return  # not one of ours (shouldn't happen — every token we mint encodes a user id)

    if event.event == "participant_joined":
        open_row = (
            db.query(LiveSessionParticipant)
            .filter(
                LiveSessionParticipant.live_session_id == session.id,
                LiveSessionParticipant.user_id == user_id,
                LiveSessionParticipant.left_at.is_(None),
            )
            .first()
        )
        if not open_row:
            db.add(
                LiveSessionParticipant(
                    live_session_id=session.id, user_id=user_id, joined_at=now,
                )
            )
        if session.status == SessionStatus.scheduled:
            session.status = SessionStatus.live
        db.commit()
        return

    if event.event == "participant_left":
        open_row = (
            db.query(LiveSessionParticipant)
            .filter(
                LiveSessionParticipant.live_session_id == session.id,
                LiveSessionParticipant.user_id == user_id,
                LiveSessionParticipant.left_at.is_(None),
            )
            .first()
        )
        if open_row:
            open_row.left_at = now
            open_row.duration_sec += max(0, int((now - open_row.joined_at).total_seconds()))
            db.flush()
            content_progress.sync_meeting_attendance(db, session, user_id)
        db.commit()
        return


def _close_dangling_participants(db: Session, session: LiveSession, now: datetime) -> None:
    """A room_finished event means every still-open attendance row must be closed —
    LiveKit doesn't always emit an individual participant_left for everyone when
    the whole room is torn down (e.g. server-initiated end)."""
    open_rows = (
        db.query(LiveSessionParticipant)
        .filter(
            LiveSessionParticipant.live_session_id == session.id,
            LiveSessionParticipant.left_at.is_(None),
        )
        .all()
    )
    for row in open_rows:
        row.left_at = now
        row.duration_sec += max(0, int((now - row.joined_at).total_seconds()))
        db.flush()
        content_progress.sync_meeting_attendance(db, session, row.user_id)
