from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, model_validator
from app.models.live_session import SessionMode, SessionStatus, SessionParticipantRole


class SessionAudienceRuleCreate(BaseModel):
    discipline_id: Optional[int] = None
    level_id: Optional[int] = None
    user_id: Optional[int] = None

    @model_validator(mode="after")
    def exactly_one(self):
        set_count = sum(x is not None for x in (self.discipline_id, self.level_id, self.user_id))
        if set_count != 1:
            raise ValueError("Exactly one of discipline_id, level_id, user_id must be set")
        return self


class SessionAudienceRuleRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    discipline_id: Optional[int] = None
    level_id: Optional[int] = None
    user_id: Optional[int] = None


class LiveSessionCreate(BaseModel):
    mode: SessionMode = SessionMode.meeting
    start_at: datetime
    end_at: datetime
    timezone: str = "UTC"
    join_before_start_min: int = 10
    host_user_id: Optional[int] = None
    waiting_room_enabled: bool = False
    max_participants: Optional[int] = None

    @model_validator(mode="after")
    def end_after_start(self):
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class LiveSessionUpdate(BaseModel):
    mode: Optional[SessionMode] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    timezone: Optional[str] = None
    join_before_start_min: Optional[int] = None
    host_user_id: Optional[int] = None
    waiting_room_enabled: Optional[bool] = None
    max_participants: Optional[int] = None


class LiveSessionRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    content_item_id: int
    room_name: str
    mode: SessionMode
    status: SessionStatus
    start_at: datetime
    end_at: datetime
    timezone: str
    join_before_start_min: int
    host_user_id: Optional[int] = None
    waiting_room_enabled: bool
    max_participants: Optional[int] = None
    audience_rules: List[SessionAudienceRuleRead] = []


class ParticipantRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    role: SessionParticipantRole
    joined_at: datetime
    left_at: Optional[datetime] = None
    duration_sec: int


class JoinEligibility(BaseModel):
    eligible: bool
    reason: Optional[str] = None
    session: Optional[LiveSessionRead] = None
    seconds_until_join_opens: Optional[int] = None


class JoinResponse(BaseModel):
    livekit_url: str
    token: str
    room_name: str
    identity: str
    role: str
