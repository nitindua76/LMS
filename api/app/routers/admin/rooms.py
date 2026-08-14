"""
Admin moderation surface for everything currently live — both Instant Rooms
and scheduled LiveSessions, normalized into one dashboard. Every action here
is metadata/control-plane only (end, mute a specific track, remove a
participant, broadcast a text message) — never audio/video access to a
room's actual content. See the design discussion this replaced ("silently
join to judge if a session is official or personal") for why: an admin's
presence in a room must always be visible to that room's participants, and
the correct way to flag a concerning session is a visible broadcast message
or ending it, not covert listening.
"""
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import require_admin, verify_csrf, get_conferencing_client
from app.conferencing import ConferencingClient
from app.models.user import User
from app.models.instant_room import InstantRoom, InstantRoomParticipant
from app.models.live_session import LiveSession, LiveSessionParticipant, SessionStatus
from app.schemas.admin_rooms import LiveRoomSummary, LiveParticipant, BroadcastRequest, EndAllResponse
from app.services import live_session_identity as identity_svc
from app.services.audit import audit

router = APIRouter(prefix="/admin/rooms", tags=["admin-rooms"])


def _instant_room_summary(room: InstantRoom) -> LiveRoomSummary:
    open_rows = [p for p in room.participants if p.left_at is None]
    return LiveRoomSummary(
        kind="instant_room", id=room.id, room_name=room.room_name, title=room.name,
        owner_or_host_name=room.owner.name,
        participant_count=len(open_rows),
        camera_count=sum(1 for p in open_rows if p.camera_on),
        screen_share_count=sum(1 for p in open_rows if p.screen_sharing),
        started_at=min((p.joined_at for p in open_rows), default=None),
        participants=[
            LiveParticipant(
                user_id=p.user_id, name=p.user.name, email=p.user.email, joined_at=p.joined_at,
                camera_on=p.camera_on, mic_on=p.mic_on, screen_sharing=p.screen_sharing, admitted=p.admitted,
            )
            for p in open_rows
        ],
    )


def _live_session_summary(session: LiveSession) -> LiveRoomSummary:
    open_rows = [p for p in session.participants if p.left_at is None]
    return LiveRoomSummary(
        kind="live_session", id=session.id, room_name=session.room_name,
        title=f"{session.content_item.section.course.title} — {session.content_item.section.title}",
        owner_or_host_name=session.host.name if session.host else "—",
        participant_count=len(open_rows),
        camera_count=0,  # LiveSessionParticipant has no camera/mic tracking (not needed for training attendance)
        screen_share_count=0,
        started_at=min((p.joined_at for p in open_rows), default=None),
        participants=[
            LiveParticipant(
                user_id=p.user_id, name=p.user.name, email=p.user.email, joined_at=p.joined_at,
                camera_on=False, mic_on=False, screen_sharing=False, admitted=True,
            )
            for p in open_rows
        ],
    )


@router.get("", response_model=List[LiveRoomSummary])
def list_live_rooms(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Everything currently active, instant rooms and scheduled sessions
    together, sorted by whoever has been running longest — a room that's
    been open the longest is usually the one worth checking first."""
    instant_rooms = (
        db.query(InstantRoom)
        .options(
            joinedload(InstantRoom.owner),
            joinedload(InstantRoom.participants).joinedload(InstantRoomParticipant.user),
        )
        .filter(InstantRoom.active.is_(True))
        .all()
    )
    live_sessions = (
        db.query(LiveSession)
        .options(
            joinedload(LiveSession.host),
            joinedload(LiveSession.content_item),
            joinedload(LiveSession.participants).joinedload(LiveSessionParticipant.user),
        )
        .filter(LiveSession.status == SessionStatus.live)
        .all()
    )

    summaries = [_instant_room_summary(r) for r in instant_rooms if any(p.left_at is None for p in r.participants)]
    summaries += [_live_session_summary(s) for s in live_sessions]
    summaries.sort(key=lambda s: s.started_at or datetime.max.replace(tzinfo=timezone.utc))
    return summaries


@router.post("/{kind}/{room_id}/end", status_code=204, dependencies=[Depends(verify_csrf)])
async def end_room(
    kind: str,
    room_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
    conferencing: ConferencingClient = Depends(get_conferencing_client),
):
    room_name = await _resolve_and_end(db, kind, room_id, conferencing)
    audit(db, actor_id=actor.id, action="admin_end_room", target_type=kind, target_id=room_id,
          detail={"room_name": room_name})
    db.commit()


@router.post("/{kind}/{room_id}/remove/{target_user_id}", status_code=204, dependencies=[Depends(verify_csrf)])
async def remove_participant(
    kind: str,
    room_id: int,
    target_user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
    conferencing: ConferencingClient = Depends(get_conferencing_client),
):
    room_name = _room_name_for(db, kind, room_id)
    identity = identity_svc.make_identity(target_user_id)
    await conferencing.remove_participant(room_name, identity)
    audit(db, actor_id=actor.id, action="admin_remove_participant", target_type=kind, target_id=room_id,
          detail={"user_id": target_user_id})
    db.commit()


@router.post("/{kind}/{room_id}/broadcast", status_code=204, dependencies=[Depends(verify_csrf)])
async def broadcast_message(
    kind: str,
    room_id: int,
    body: BroadcastRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
    conferencing: ConferencingClient = Depends(get_conferencing_client),
):
    """
    Sends a visible, clearly-labeled message to every participant in the
    room right now — the intervention path for "this session looks
    off-topic" or "please wrap up," in place of an admin silently joining.
    """
    room_name = _room_name_for(db, kind, room_id)
    import json
    payload = json.dumps({"type": "admin_notice", "message": body.message, "from": "Administrator"}).encode()
    await conferencing.send_data(room_name, payload, topic="admin_notice")
    audit(db, actor_id=actor.id, action="admin_broadcast", target_type=kind, target_id=room_id,
          detail={"message": body.message})
    db.commit()


@router.post("/end-all", response_model=EndAllResponse, dependencies=[Depends(verify_csrf)])
async def end_all_rooms(
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
    conferencing: ConferencingClient = Depends(get_conferencing_client),
):
    """Acute-bandwidth-emergency lever: ends every currently active Instant
    Room and live LiveSession in one call. Does not disable creation of new
    ones — pair with the INSTANT_ROOMS_ENABLED kill switch (admin Settings
    page) for that."""
    instant_rooms = db.query(InstantRoom).filter(InstantRoom.active.is_(True)).all()
    live_sessions = db.query(LiveSession).filter(LiveSession.status == SessionStatus.live).all()

    for room in instant_rooms:
        try:
            await conferencing.end_room(room.room_name)
        except Exception:
            pass
        room.active = False
        room.ended_at = datetime.now(timezone.utc)

    for session in live_sessions:
        try:
            await conferencing.end_room(session.room_name)
        except Exception:
            pass
        session.status = SessionStatus.ended

    audit(db, actor_id=actor.id, action="admin_end_all_rooms", target_type="system", target_id=None,
          detail={"rooms_ended": len(instant_rooms), "sessions_ended": len(live_sessions)})
    db.commit()
    return EndAllResponse(rooms_ended=len(instant_rooms), sessions_ended=len(live_sessions))


def _room_name_for(db: Session, kind: str, room_id: int) -> str:
    if kind == "instant_room":
        room = db.get(InstantRoom, room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        return room.room_name
    if kind == "live_session":
        session = db.get(LiveSession, room_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session.room_name
    raise HTTPException(status_code=422, detail="kind must be instant_room or live_session")


async def _resolve_and_end(db: Session, kind: str, room_id: int, conferencing: ConferencingClient) -> str:
    if kind == "instant_room":
        room = db.get(InstantRoom, room_id)
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        try:
            await conferencing.end_room(room.room_name)
        except Exception:
            pass
        room.active = False
        room.ended_at = datetime.now(timezone.utc)
        return room.room_name
    if kind == "live_session":
        session = db.get(LiveSession, room_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        try:
            await conferencing.end_room(session.room_name)
        except Exception:
            pass
        session.status = SessionStatus.ended
        return session.room_name
    raise HTTPException(status_code=422, detail="kind must be instant_room or live_session")
