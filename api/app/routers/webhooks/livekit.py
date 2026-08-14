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
from app.models.instant_room import InstantRoom, InstantRoomParticipant
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
    if session is None:
        # Not a scheduled training session's room — check whether it's an
        # Instant Room instead. The two features share one LiveKit server
        # and one webhook endpoint, so every room name has to be checked
        # against both tables; a room_name is never valid in both, since
        # InstantRoom.room_name and LiveSession.room_name are independently
        # generated (see make_room_name-style prefixes: "instant-" vs the
        # scheduling flow's own scheme).
        return await _handle_instant_room_event(db, event)

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


async def _handle_instant_room_event(db: Session, event) -> None:
    """
    Instant Room counterpart to the LiveSession handling above — same event
    types, but writes to InstantRoomParticipant instead, and additionally
    tracks live camera/mic/screen-share state (track_published/
    track_unpublished) for the admin Live Sessions dashboard. No
    ContentProgress/attendance-completion integration here — Instant Rooms
    have no compliance semantics (see models/instant_room.py's module
    docstring for why this is deliberately not the same table/logic).
    """
    room = db.query(InstantRoom).filter(InstantRoom.room_name == event.room_name).first()
    if not room:
        return  # neither a LiveSession nor an InstantRoom room — nothing to do

    now = datetime.now(timezone.utc)

    if event.event == "room_finished":
        room.active = False
        room.ended_at = now
        _close_dangling_room_participants(db, room, now)
        db.commit()
        return

    if event.event == "room_started":
        db.commit()
        return

    if event.participant is None:
        return
    user_id = parse_identity(event.participant.identity)
    if user_id is None:
        return

    if event.event == "participant_joined":
        open_row = db.query(InstantRoomParticipant).filter(
            InstantRoomParticipant.room_id == room.id,
            InstantRoomParticipant.user_id == user_id,
            InstantRoomParticipant.left_at.is_(None),
        ).first()
        if not open_row:
            # A row may already exist from the join endpoint itself
            # (routers/employee/rooms.py sets admitted based on admit_mode
            # before the client even connects) — only create one here if
            # somehow missed, defaulting to admitted since automatic-mode
            # rooms have no waiting state at all.
            db.add(InstantRoomParticipant(room_id=room.id, user_id=user_id, joined_at=now, admitted=True))
        db.commit()
        return

    if event.event == "participant_left":
        open_row = db.query(InstantRoomParticipant).filter(
            InstantRoomParticipant.room_id == room.id,
            InstantRoomParticipant.user_id == user_id,
            InstantRoomParticipant.left_at.is_(None),
        ).first()
        if open_row:
            open_row.left_at = now
            open_row.duration_sec += max(0, int((now - open_row.joined_at).total_seconds()))
            db.flush()
        db.commit()
        return

    if event.event in ("track_published", "track_unpublished") and event.track:
        open_row = db.query(InstantRoomParticipant).filter(
            InstantRoomParticipant.room_id == room.id,
            InstantRoomParticipant.user_id == user_id,
            InstantRoomParticipant.left_at.is_(None),
        ).first()
        if open_row:
            is_on = event.event == "track_published"
            if event.track.source == "camera":
                open_row.camera_on = is_on
            elif event.track.source == "microphone":
                open_row.mic_on = is_on
            elif event.track.source == "screen_share":
                open_row.screen_sharing = is_on
            db.commit()
        return


def _close_dangling_room_participants(db: Session, room: InstantRoom, now: datetime) -> None:
    open_rows = db.query(InstantRoomParticipant).filter(
        InstantRoomParticipant.room_id == room.id,
        InstantRoomParticipant.left_at.is_(None),
    ).all()
    for row in open_rows:
        row.left_at = now
        row.duration_sec += max(0, int((now - row.joined_at).total_seconds()))
        db.flush()
