from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, field_validator
from app.models.instant_room import RoomAdmitMode


class InstantRoomCreate(BaseModel):
    name: str
    admit_mode: RoomAdmitMode = RoomAdmitMode.automatic
    is_standing_room: bool = True

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be empty")
        return v


class InstantRoomUpdate(BaseModel):
    name: Optional[str] = None
    admit_mode: Optional[RoomAdmitMode] = None


class MemberRead(BaseModel):
    id: int
    user_id: int
    name: str
    email: str
    added_via_cpf: bool


class RoomGroupTargetRead(BaseModel):
    id: int
    group_id: int
    group_name: str
    member_count: int


class RoomGroupTargetCreate(BaseModel):
    group_id: int


class GroupSearchResult(BaseModel):
    """Minimal shape for the typeahead group-attach UI — never exposes a
    group's rule definitions, just enough to pick one."""
    id: int
    name: str
    member_count: int


class InstantRoomRead(BaseModel):
    id: int
    owner_user_id: int
    owner_name: str
    name: str
    room_name: str
    admit_mode: RoomAdmitMode
    is_standing_room: bool
    active: bool
    created_at: datetime
    members: List[MemberRead] = []
    group_targets: List[RoomGroupTargetRead] = []
    is_owner: bool = False
    # Shareable link anyone with room access can use to join directly (see
    # routers/employee/rooms.py's _join_url) — used by the "Copy link"
    # button and as the {link} substituted into the auto-mail-on-invite.
    join_url: str = ""


class MemberAddByUser(BaseModel):
    user_id: int


class MemberAddByCpf(BaseModel):
    cpf: str

    @field_validator("cpf")
    @classmethod
    def cpf_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("cpf cannot be empty")
        return v


class RoomJoinResponse(BaseModel):
    livekit_url: str
    token: str
    room_name: str
    identity: str
    is_host: bool
    admitted: bool  # False means the client should show a "waiting for host" state


class PendingParticipant(BaseModel):
    user_id: int
    name: str
    email: str
    joined_at: datetime
