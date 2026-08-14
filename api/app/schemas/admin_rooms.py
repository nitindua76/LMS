from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class LiveParticipant(BaseModel):
    user_id: int
    name: str
    email: str
    joined_at: datetime
    camera_on: bool
    mic_on: bool
    screen_sharing: bool
    admitted: bool


class LiveRoomSummary(BaseModel):
    """One row on the admin Live Sessions dashboard — an active InstantRoom
    or a live LiveSession, normalized to the same shape so both can be
    listed together."""
    kind: str  # "instant_room" | "live_session"
    id: int
    room_name: str
    title: str
    owner_or_host_name: str
    participant_count: int
    camera_count: int
    screen_share_count: int
    started_at: Optional[datetime] = None
    participants: List[LiveParticipant] = []


class BroadcastRequest(BaseModel):
    message: str


class EndAllResponse(BaseModel):
    rooms_ended: int
    sessions_ended: int
