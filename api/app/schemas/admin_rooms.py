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


class HistoryParticipant(BaseModel):
    """Attendance record for one past session/room — the same
    camera_on/mic_on/screen_sharing snapshot LiveParticipant uses for LIVE
    rooms, plus left_at/duration_sec since history is about what already
    happened, not what's happening right now."""
    user_id: int
    name: str
    email: str
    joined_at: datetime
    left_at: Optional[datetime] = None
    duration_sec: int
    camera_on: bool
    mic_on: bool
    screen_sharing: bool


class SessionHistoryRow(BaseModel):
    """One row in the admin Session History list — a PAST (ended/
    cancelled) InstantRoom or LiveSession, normalized the same way
    LiveRoomSummary normalizes currently-active ones."""
    kind: str  # "instant_room" | "live_session"
    id: int
    room_name: str
    title: str
    owner_or_host_name: str
    status: str  # instant_room: "ended"; live_session: "ended"|"cancelled"
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    participant_count: int
    screen_share_count: int
    max_concurrent: int


class SessionHistoryDetail(SessionHistoryRow):
    participants: List[HistoryParticipant] = []


class SessionHistoryPage(BaseModel):
    items: List[SessionHistoryRow]
    total: int
    page: int
    page_size: int
