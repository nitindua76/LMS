"""Generic value types shared by client.py and webhooks.py — no LMS concepts."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ParticipantPermissions:
    """
    What one participant is allowed to do in a room. The mapping from an LMS
    concept (session mode + participant role) to a ParticipantPermissions
    value is policy that belongs to the caller, not to this module.
    """
    can_publish: bool = True
    can_subscribe: bool = True
    can_publish_data: bool = True
    room_admin: bool = False
    # Hidden participants (typically webinar attendees) don't appear in the
    # room's participant list to other clients and cannot publish tracks.
    hidden: bool = False


@dataclass(frozen=True)
class ParticipantToken:
    token: str
    identity: str
    room_name: str
    expires_in_sec: int


@dataclass(frozen=True)
class RoomInfo:
    name: str
    num_participants: int
    creation_unix_time: int


@dataclass(frozen=True)
class WebhookParticipant:
    identity: str
    name: Optional[str] = None


@dataclass(frozen=True)
class WebhookEvent:
    """
    Normalized shape of the LiveKit webhook events this app cares about.
    `event` is one of: participant_joined, participant_left, room_started,
    room_finished. Anything else is parsed but the caller may ignore it.
    """
    event: str
    room_name: str
    participant: Optional[WebhookParticipant] = None
    raw_event_id: str = field(default="")
