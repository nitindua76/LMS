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
from app.schemas.admin_rooms import (
    LiveRoomSummary, LiveParticipant, BroadcastRequest, EndAllResponse,
    SessionHistoryRow, SessionHistoryDetail, SessionHistoryPage, HistoryParticipant,
)
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
        camera_count=sum(1 for p in open_rows if p.camera_on),
        screen_share_count=sum(1 for p in open_rows if p.screen_sharing),
        started_at=min((p.joined_at for p in open_rows), default=None),
        participants=[
            LiveParticipant(
                user_id=p.user_id, name=p.user.name, email=p.user.email, joined_at=p.joined_at,
                camera_on=p.camera_on, mic_on=p.mic_on, screen_sharing=p.screen_sharing, admitted=True,
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


def _max_concurrent(intervals: List[tuple]) -> int:
    """Peak simultaneous occupancy from a list of (joined_at, left_at)
    pairs — a simple sweep over start/end events. left_at=None (still
    open) is treated as 'now' by the caller before this is invoked; every
    row passed to this function is already closed for history purposes."""
    events = []
    for start, end in intervals:
        events.append((start, 1))
        events.append((end, -1))
    events.sort(key=lambda e: (e[0], -e[1]))  # process arrivals before departures at the same instant
    current = peak = 0
    for _time, delta in events:
        current += delta
        peak = max(peak, current)
    return peak


def _instant_room_history_row(room: InstantRoom) -> SessionHistoryRow:
    rows = room.participants
    closed = [p for p in rows if p.left_at is not None]
    started_at = min((p.joined_at for p in rows), default=room.created_at)
    return SessionHistoryRow(
        kind="instant_room", id=room.id, room_name=room.room_name, title=room.name,
        owner_or_host_name=room.owner.name, status="ended",
        started_at=started_at, ended_at=room.ended_at,
        participant_count=len({p.user_id for p in rows}),
        screen_share_count=sum(1 for p in rows if p.screen_sharing),
        max_concurrent=_max_concurrent([(p.joined_at, p.left_at) for p in closed]) if closed else (1 if rows else 0),
    )


def _live_session_history_row(session: LiveSession) -> SessionHistoryRow:
    rows = session.participants
    closed = [p for p in rows if p.left_at is not None]
    started_at = min((p.joined_at for p in rows), default=session.start_at)
    # LiveSession has no actual "ended at" audit column (only the scheduled
    # end_at) — approximate with the last participant to leave, falling
    # back to the scheduled end time when that's unavailable (e.g. nobody
    # ever actually joined before it got cancelled).
    ended_at = max((p.left_at for p in closed), default=None) or session.end_at
    return SessionHistoryRow(
        kind="live_session", id=session.id, room_name=session.room_name,
        title=f"{session.content_item.section.course.title} — {session.content_item.section.title}",
        owner_or_host_name=session.host.name if session.host else "—",
        status=session.status.value,
        started_at=started_at, ended_at=ended_at,
        participant_count=len({p.user_id for p in rows}),
        screen_share_count=sum(1 for p in rows if p.screen_sharing),
        max_concurrent=_max_concurrent([(p.joined_at, p.left_at) for p in closed]) if closed else 0,
    )


@router.get("/history", response_model=SessionHistoryPage)
def list_session_history(
    page: int = 1,
    page_size: int = 20,
    kind: str = "",
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Everything that has ALREADY happened — ended/cancelled LiveSessions and
    Instant Rooms no longer active — the counterpart to list_live_rooms
    (which only shows what's active right now). This is the "no option for
    admin to see previous sessions" gap: previously the only historical
    view was per-course (MeetingSessionPanel.tsx, requires navigating into
    one specific content item) or nothing at all for Instant Rooms.
    """
    if kind not in ("", "instant_room", "live_session"):
        raise HTTPException(status_code=422, detail="kind must be instant_room or live_session")

    rows: List[SessionHistoryRow] = []

    if kind in ("", "instant_room"):
        instant_rooms = (
            db.query(InstantRoom)
            .options(
                joinedload(InstantRoom.owner),
                joinedload(InstantRoom.participants).joinedload(InstantRoomParticipant.user),
            )
            .filter(InstantRoom.active.is_(False))
            .all()
        )
        rows += [_instant_room_history_row(r) for r in instant_rooms]

    if kind in ("", "live_session"):
        live_sessions = (
            db.query(LiveSession)
            .options(
                joinedload(LiveSession.host),
                joinedload(LiveSession.content_item),
                joinedload(LiveSession.participants).joinedload(LiveSessionParticipant.user),
            )
            .filter(LiveSession.status.in_([SessionStatus.ended, SessionStatus.cancelled]))
            .all()
        )
        rows += [_live_session_history_row(s) for s in live_sessions]

    # Most recently ended first — deliberately falls back to started_at when
    # ended_at is unavailable (never None in practice here, but keeps sort
    # stable rather than crashing on a stray None).
    rows.sort(key=lambda r: r.ended_at or r.started_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start:start + page_size]
    return SessionHistoryPage(items=page_rows, total=total, page=page, page_size=page_size)


@router.get("/history/{kind}/{room_id}", response_model=SessionHistoryDetail)
def get_session_history_detail(
    kind: str,
    room_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Drill-down: full per-participant attendance/screen-share/timing
    detail for one past session/room."""
    if kind == "instant_room":
        room = (
            db.query(InstantRoom)
            .options(
                joinedload(InstantRoom.owner),
                joinedload(InstantRoom.participants).joinedload(InstantRoomParticipant.user),
            )
            .filter(InstantRoom.id == room_id)
            .first()
        )
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        base = _instant_room_history_row(room)
        participants = [
            HistoryParticipant(
                user_id=p.user_id, name=p.user.name, email=p.user.email,
                joined_at=p.joined_at, left_at=p.left_at, duration_sec=p.duration_sec,
                camera_on=p.camera_on, mic_on=p.mic_on, screen_sharing=p.screen_sharing,
            )
            for p in sorted(room.participants, key=lambda p: p.joined_at)
        ]
    elif kind == "live_session":
        session = (
            db.query(LiveSession)
            .options(
                joinedload(LiveSession.host),
                joinedload(LiveSession.content_item),
                joinedload(LiveSession.participants).joinedload(LiveSessionParticipant.user),
            )
            .filter(LiveSession.id == room_id)
            .first()
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        base = _live_session_history_row(session)
        participants = [
            HistoryParticipant(
                user_id=p.user_id, name=p.user.name, email=p.user.email,
                joined_at=p.joined_at, left_at=p.left_at, duration_sec=p.duration_sec,
                camera_on=p.camera_on, mic_on=p.mic_on, screen_sharing=p.screen_sharing,
            )
            for p in sorted(session.participants, key=lambda p: p.joined_at)
        ]
    else:
        raise HTTPException(status_code=422, detail="kind must be instant_room or live_session")

    return SessionHistoryDetail(**base.model_dump(), participants=participants)


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
