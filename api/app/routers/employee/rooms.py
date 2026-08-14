"""
Instant Rooms — employee-facing endpoints for day-to-day meeting rooms.
Deliberately available to ANY authenticated user (admin or employee), not
gated by require_employee — this is the feature meant to drive daily use
across the whole organization, not just the training-content audience.
"""
import secrets
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_current_user, verify_csrf, get_conferencing_client
from app.conferencing import ConferencingClient, ParticipantPermissions
from app.models.employee_group import EmployeeGroup
from app.models.user import User
from app.models.instant_room import (
    InstantRoom, InstantRoomMember, InstantRoomParticipant, InstantRoomGroupTarget, RoomAdmitMode,
)
from app.schemas.instant_room import (
    InstantRoomCreate, InstantRoomRead, MemberRead, MemberAddByUser, MemberAddByCpf,
    RoomJoinResponse, PendingParticipant, RoomGroupTargetRead, RoomGroupTargetCreate, GroupSearchResult,
)
from app.services import live_session_identity as identity_svc
from app.services import mail_api
from app.services.audit import audit
from app.services.employee_groups import user_matches_group, count_group_members, InvalidRuleError
from app.services.provisioning import get_or_provision_by_cpf
from app.services.settings_service import get_setting, get_setting_bool
from app.services.sso import get_employee_api_client
from app.config import settings

router = APIRouter(prefix="/my/rooms", tags=["employee-rooms"])


def _rooms_enabled(db: Session) -> bool:
    return get_setting_bool(db, "INSTANT_ROOMS_ENABLED", settings.INSTANT_ROOMS_ENABLED)


def _require_rooms_enabled(db: Session) -> None:
    if not _rooms_enabled(db):
        raise HTTPException(status_code=503, detail="Instant Rooms are temporarily disabled by an administrator")


def _load_room(db: Session, room_id: int) -> InstantRoom:
    room = (
        db.query(InstantRoom)
        .options(
            joinedload(InstantRoom.members).joinedload(InstantRoomMember.user),
            joinedload(InstantRoom.owner),
            joinedload(InstantRoom.group_targets).joinedload(InstantRoomGroupTarget.group),
        )
        .filter(InstantRoom.id == room_id)
        .first()
    )
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room


def _can_see_room(db: Session, room: InstantRoom, user: User) -> bool:
    if room.owner_user_id == user.id or any(m.user_id == user.id for m in room.members):
        return True
    # Additive group-based access — anyone currently matching ANY group
    # targeted at this room, resolved live (never materialized), same
    # principle as CourseTargetGroup for courses.
    for target in room.group_targets:
        try:
            if user_matches_group(db, user, target.group):
                return True
        except InvalidRuleError:
            continue
    return False


def _join_url(db: Session, room: InstantRoom) -> str:
    base = get_setting(db, "FRONTEND_URL", settings.FRONTEND_URL).rstrip("/")
    return f"{base}/join/{room.id}"


def _to_read(db: Session, room: InstantRoom, current_user: User) -> InstantRoomRead:
    group_targets = []
    for t in room.group_targets:
        try:
            count = count_group_members(db, t.group)
        except InvalidRuleError:
            count = 0
        group_targets.append(RoomGroupTargetRead(id=t.id, group_id=t.group_id, group_name=t.group.name, member_count=count))
    return InstantRoomRead(
        id=room.id, owner_user_id=room.owner_user_id, owner_name=room.owner.name,
        name=room.name, room_name=room.room_name, admit_mode=room.admit_mode,
        is_standing_room=room.is_standing_room, active=room.active, created_at=room.created_at,
        members=[
            MemberRead(id=m.id, user_id=m.user_id, name=m.user.name, email=m.user.email, added_via_cpf=m.added_via_cpf)
            for m in room.members
        ],
        group_targets=group_targets,
        is_owner=room.owner_user_id == current_user.id,
        join_url=_join_url(db, room),
    )


@router.get("", response_model=List[InstantRoomRead])
def list_my_rooms(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Rooms the user owns, is individually a member of, or currently
    matches a group targeted at (resolved live, same as course/session
    group-targeting elsewhere)."""
    owned = db.query(InstantRoom).filter(InstantRoom.owner_user_id == user.id).all()
    member_of = (
        db.query(InstantRoom)
        .join(InstantRoomMember, InstantRoomMember.room_id == InstantRoom.id)
        .filter(InstantRoomMember.user_id == user.id)
        .all()
    )
    group_targeted = (
        db.query(InstantRoom)
        .join(InstantRoomGroupTarget, InstantRoomGroupTarget.room_id == InstantRoom.id)
        .join(EmployeeGroup, EmployeeGroup.id == InstantRoomGroupTarget.group_id)
        .all()
    )
    via_group = []
    for room in group_targeted:
        for target in room.group_targets:
            try:
                if user_matches_group(db, user, target.group):
                    via_group.append(room)
                    break
            except InvalidRuleError:
                continue

    seen_ids = set()
    rooms = []
    for room in owned + member_of + via_group:
        if room.id not in seen_ids:
            seen_ids.add(room.id)
            rooms.append(room)
    # Reload with relationships for the read schema
    if not rooms:
        return []
    full = (
        db.query(InstantRoom)
        .options(
            joinedload(InstantRoom.members).joinedload(InstantRoomMember.user),
            joinedload(InstantRoom.owner),
            joinedload(InstantRoom.group_targets).joinedload(InstantRoomGroupTarget.group),
        )
        .filter(InstantRoom.id.in_([r.id for r in rooms]))
        .order_by(InstantRoom.created_at.desc())
        .all()
    )
    return [_to_read(db, r, user) for r in full]


@router.get("/{room_id}", response_model=InstantRoomRead)
def get_room(
    room_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Resolve a single room by id — what the shareable join link
    (/join/{room_id} in the frontend) uses to show the room before
    actually joining. 403s for anyone not the owner or an invited member,
    same visibility rule as everywhere else."""
    room = _load_room(db, room_id)
    if room.owner_user_id != user.id and not _can_see_room(db, room, user):
        raise HTTPException(status_code=403, detail="You have not been added to this room")
    return _to_read(db, room, user)


@router.post("", response_model=InstantRoomRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(verify_csrf)])
def create_room(
    body: InstantRoomCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _require_rooms_enabled(db)
    if not user.can_create_rooms:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your room-creation privilege has been revoked by an administrator",
        )

    room_name = f"instant-{user.id}-{secrets.token_hex(6)}"
    room = InstantRoom(
        owner_user_id=user.id, name=body.name, room_name=room_name,
        admit_mode=body.admit_mode, is_standing_room=body.is_standing_room,
    )
    db.add(room)
    db.flush()
    audit(db, actor_id=user.id, action="create_instant_room", target_type="instant_room",
          target_id=room.id, detail={"name": room.name})
    db.commit()
    return _to_read(db, _load_room(db, room.id), user)


@router.delete("/{room_id}", status_code=204, dependencies=[Depends(verify_csrf)])
def delete_room(
    room_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    room = db.get(InstantRoom, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the room owner can delete it")
    db.delete(room)
    audit(db, actor_id=user.id, action="delete_instant_room", target_type="instant_room", target_id=room_id)
    db.commit()


# ── Membership ───────────────────────────────────────────────────────────────

@router.post("/{room_id}/members", response_model=MemberRead, status_code=201,
             dependencies=[Depends(verify_csrf)])
def add_member_by_user(
    room_id: int,
    body: MemberAddByUser,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    room = db.get(InstantRoom, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the room owner can manage members")

    target = db.get(User, body.user_id)
    if not target:
        raise HTTPException(status_code=422, detail="User not found")
    return _add_member(db, room, target, added_via_cpf=False, actor_id=user.id)


@router.post("/{room_id}/members/by-cpf", response_model=MemberRead, status_code=201,
             dependencies=[Depends(verify_csrf)])
def add_member_by_cpf(
    room_id: int,
    body: MemberAddByCpf,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Adds (auto-provisioning if needed) an employee by CPF, even if they've
    never logged in — the same shared helper used for course/group
    targeting (see services/provisioning.py), not a separate implementation.
    """
    room = db.get(InstantRoom, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the room owner can manage members")

    target = get_or_provision_by_cpf(db, body.cpf, employee_client=get_employee_api_client(db))
    return _add_member(db, room, target, added_via_cpf=True, actor_id=user.id)


def _add_member(db: Session, room: InstantRoom, target: User, *, added_via_cpf: bool, actor_id: int) -> MemberRead:
    existing = db.query(InstantRoomMember).filter(
        InstantRoomMember.room_id == room.id, InstantRoomMember.user_id == target.id,
    ).first()
    if existing:
        return MemberRead(id=existing.id, user_id=target.id, name=target.name, email=target.email, added_via_cpf=existing.added_via_cpf)

    member = InstantRoomMember(room_id=room.id, user_id=target.id, added_via_cpf=added_via_cpf)
    db.add(member)
    db.flush()
    audit(db, actor_id=actor_id, action="add_instant_room_member", target_type="instant_room",
          target_id=room.id, detail={"user_id": target.id, "added_via_cpf": added_via_cpf})
    db.commit()

    # Best-effort: mail the newly-added member their join link. Uses the
    # TARGET's own email (not the room owner's) — see mail_api.py for why a
    # still-unresolved CPF placeholder email is silently skipped rather
    # than mailing a bounce-guaranteed address.
    try:
        mail_api.send_meeting_link_email(
            db, to_email=target.email, link=_join_url(db, room), room_name=room.name,
        )
    except Exception:
        pass  # never let a mail failure affect the member-add response

    return MemberRead(id=member.id, user_id=target.id, name=target.name, email=target.email, added_via_cpf=added_via_cpf)


@router.get("/groups/search", response_model=List[GroupSearchResult])
def search_groups(
    q: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Typeahead search for the group-attach UI — deliberately available to
    ANY authenticated user (a room owner can be an ordinary employee, not
    just an admin), unlike the full admin Employee Groups management API
    (create/edit/delete rules stays admin-only). Returns just enough to
    pick a group: id, name, live member count — never the rule
    definitions themselves.
    """
    query = db.query(EmployeeGroup)
    if q.strip():
        query = query.filter(EmployeeGroup.name.ilike(f"%{q.strip()}%"))
    groups = query.order_by(EmployeeGroup.name).limit(20).all()
    out = []
    for g in groups:
        try:
            count = count_group_members(db, g)
        except InvalidRuleError:
            count = 0
        out.append(GroupSearchResult(id=g.id, name=g.name, member_count=count))
    return out


@router.get("/{room_id}/group-targets", response_model=List[RoomGroupTargetRead])
def list_room_group_targets(
    room_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    room = _load_room(db, room_id)
    if room.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the room owner can manage members")
    out = []
    for t in room.group_targets:
        try:
            count = count_group_members(db, t.group)
        except InvalidRuleError:
            count = 0
        out.append(RoomGroupTargetRead(id=t.id, group_id=t.group_id, group_name=t.group.name, member_count=count))
    return out


@router.post("/{room_id}/group-targets", response_model=RoomGroupTargetRead, status_code=201,
             dependencies=[Depends(verify_csrf)])
def add_room_group_target(
    room_id: int,
    body: RoomGroupTargetCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Attaches a whole dynamic EmployeeGroup to this room — additive on top
    of individually-added members, resolved live (see _can_see_room)."""
    room = db.get(InstantRoom, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the room owner can manage members")

    group = db.get(EmployeeGroup, body.group_id)
    if not group:
        raise HTTPException(status_code=422, detail="Group not found")

    existing = db.query(InstantRoomGroupTarget).filter(
        InstantRoomGroupTarget.room_id == room_id, InstantRoomGroupTarget.group_id == body.group_id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="This group is already targeted at this room")

    target = InstantRoomGroupTarget(room_id=room_id, group_id=body.group_id)
    db.add(target)
    db.flush()
    audit(db, actor_id=user.id, action="add_instant_room_group_target", target_type="instant_room",
          target_id=room_id, detail={"group_id": body.group_id})
    db.commit()
    try:
        count = count_group_members(db, group)
    except InvalidRuleError:
        count = 0
    return RoomGroupTargetRead(id=target.id, group_id=group.id, group_name=group.name, member_count=count)


@router.delete("/{room_id}/group-targets/{target_id}", status_code=204, dependencies=[Depends(verify_csrf)])
def remove_room_group_target(
    room_id: int,
    target_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    room = db.get(InstantRoom, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the room owner can manage members")
    target = db.query(InstantRoomGroupTarget).filter(
        InstantRoomGroupTarget.id == target_id, InstantRoomGroupTarget.room_id == room_id,
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="Group target not found")
    db.delete(target)
    audit(db, actor_id=user.id, action="remove_instant_room_group_target", target_type="instant_room",
          target_id=room_id, detail={"target_id": target_id})
    db.commit()


@router.delete("/{room_id}/members/{member_id}", status_code=204, dependencies=[Depends(verify_csrf)])
def remove_member(
    room_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    room = db.get(InstantRoom, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the room owner can manage members")
    member = db.query(InstantRoomMember).filter(
        InstantRoomMember.id == member_id, InstantRoomMember.room_id == room_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    db.delete(member)
    audit(db, actor_id=user.id, action="remove_instant_room_member", target_type="instant_room",
          target_id=room_id, detail={"member_id": member_id})
    db.commit()


# ── Join / admit / decline / end ─────────────────────────────────────────────

@router.post("/{room_id}/join", response_model=RoomJoinResponse, dependencies=[Depends(verify_csrf)])
async def join_room(
    room_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    conferencing: ConferencingClient = Depends(get_conferencing_client),
):
    _require_rooms_enabled(db)
    room = _load_room(db, room_id)
    is_host = room.owner_user_id == user.id
    if not is_host and not _can_see_room(db, room, user):
        raise HTTPException(status_code=403, detail="You have not been added to this room")

    if not room.active:
        if not is_host:
            # Ending a room is never a permanent dead-end — only deleting it
            # is. A room the host previously ended just needs the host to
            # join again to reopen it; a non-host arriving while it's
            # closed just has to wait for that, same as any meeting that
            # hasn't started yet.
            raise HTTPException(status_code=409, detail="This room hasn't been started yet — ask the host to join first")
        room.active = True
        room.ended_at = None

    now = datetime.now(timezone.utc)
    open_row = db.query(InstantRoomParticipant).filter(
        InstantRoomParticipant.room_id == room.id,
        InstantRoomParticipant.user_id == user.id,
        InstantRoomParticipant.left_at.is_(None),
    ).first()

    needs_admit = room.admit_mode == RoomAdmitMode.manual and not is_host
    if not open_row:
        open_row = InstantRoomParticipant(
            room_id=room.id, user_id=user.id, joined_at=now, admitted=not needs_admit,
        )
        db.add(open_row)
        db.flush()

    permissions = ParticipantPermissions(
        can_publish=not needs_admit or open_row.admitted,
        can_subscribe=not needs_admit or open_row.admitted,
        can_publish_data=True,
        room_admin=is_host,
        hidden=needs_admit and not open_row.admitted,
    )
    identity = identity_svc.make_identity(user.id)
    token = conferencing.generate_token(room.room_name, identity, user.name, permissions)
    db.commit()

    return RoomJoinResponse(
        livekit_url=settings.LIVEKIT_URL, token=token.token, room_name=room.room_name,
        identity=identity, is_host=is_host, admitted=open_row.admitted,
    )


@router.get("/{room_id}/pending", response_model=List[PendingParticipant])
def list_pending(
    room_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Host-only: who's currently waiting to be admitted."""
    room = db.get(InstantRoom, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the room owner can view the waiting room")
    rows = (
        db.query(InstantRoomParticipant)
        .options(joinedload(InstantRoomParticipant.user))
        .filter(
            InstantRoomParticipant.room_id == room_id,
            InstantRoomParticipant.admitted.is_(False),
            InstantRoomParticipant.left_at.is_(None),
        )
        .all()
    )
    return [
        PendingParticipant(user_id=r.user_id, name=r.user.name, email=r.user.email, joined_at=r.joined_at)
        for r in rows
    ]


@router.post("/{room_id}/admit/{target_user_id}", status_code=204, dependencies=[Depends(verify_csrf)])
async def admit_participant(
    room_id: int,
    target_user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    conferencing: ConferencingClient = Depends(get_conferencing_client),
):
    room = db.get(InstantRoom, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the room owner can admit participants")

    row = db.query(InstantRoomParticipant).filter(
        InstantRoomParticipant.room_id == room_id,
        InstantRoomParticipant.user_id == target_user_id,
        InstantRoomParticipant.left_at.is_(None),
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="This participant is not waiting")

    row.admitted = True
    db.flush()
    identity = identity_svc.make_identity(target_user_id)
    await conferencing.update_participant_permissions(
        room.room_name, identity,
        ParticipantPermissions(can_publish=True, can_subscribe=True, can_publish_data=True, hidden=False),
    )
    audit(db, actor_id=user.id, action="admit_instant_room_participant", target_type="instant_room",
          target_id=room_id, detail={"user_id": target_user_id})
    db.commit()


@router.post("/{room_id}/decline/{target_user_id}", status_code=204, dependencies=[Depends(verify_csrf)])
async def decline_participant(
    room_id: int,
    target_user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    conferencing: ConferencingClient = Depends(get_conferencing_client),
):
    room = db.get(InstantRoom, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the room owner can decline participants")

    row = db.query(InstantRoomParticipant).filter(
        InstantRoomParticipant.room_id == room_id,
        InstantRoomParticipant.user_id == target_user_id,
        InstantRoomParticipant.left_at.is_(None),
    ).first()
    identity = identity_svc.make_identity(target_user_id)
    try:
        await conferencing.remove_participant(room.room_name, identity)
    except Exception:
        pass  # they may have already disconnected client-side
    if row:
        now = datetime.now(timezone.utc)
        row.left_at = now
        row.duration_sec += max(0, int((now - row.joined_at).total_seconds()))
        db.flush()
    audit(db, actor_id=user.id, action="decline_instant_room_participant", target_type="instant_room",
          target_id=room_id, detail={"user_id": target_user_id})
    db.commit()


@router.post("/{room_id}/leave", status_code=204, dependencies=[Depends(verify_csrf)])
def leave_room(
    room_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Best-effort close on explicit leave — the LiveKit webhook is the
    authoritative path (see routers/webhooks/livekit.py) and will also
    close this row if the client disconnects without calling this."""
    row = db.query(InstantRoomParticipant).filter(
        InstantRoomParticipant.room_id == room_id,
        InstantRoomParticipant.user_id == user.id,
        InstantRoomParticipant.left_at.is_(None),
    ).first()
    if row:
        now = datetime.now(timezone.utc)
        row.left_at = now
        row.duration_sec += max(0, int((now - row.joined_at).total_seconds()))
        db.commit()


@router.post("/{room_id}/end", status_code=204, dependencies=[Depends(verify_csrf)])
async def end_room(
    room_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    conferencing: ConferencingClient = Depends(get_conferencing_client),
):
    room = db.get(InstantRoom, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="Only the room owner can end this room")

    try:
        await conferencing.end_room(room.room_name)
    except Exception:
        pass  # room may already be empty/gone on LiveKit's side
    room.active = False
    room.ended_at = datetime.now(timezone.utc)
    audit(db, actor_id=user.id, action="end_instant_room", target_type="instant_room", target_id=room_id)
    db.commit()
