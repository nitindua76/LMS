"""
Self-contained, product-agnostic wrapper around the LiveKit server SDK.

This package must never import anything from app.models or app.schemas —
it only knows about rooms, participants, and permissions. Session
scheduling, audience targeting, and completion tracking are LMS concerns
and live in app/routers/{admin,employee}/sessions.py and
app/routers/webhooks/livekit.py, which call into this package rather than
the other way around. Keeping the boundary one-directional is what lets
this package be lifted into its own service later without a rewrite.
"""
from .schemas import ParticipantPermissions, ParticipantToken, RoomInfo
from .client import ConferencingClient
from .webhooks import verify_and_parse_webhook, WebhookEvent

__all__ = [
    "ParticipantPermissions",
    "ParticipantToken",
    "RoomInfo",
    "ConferencingClient",
    "verify_and_parse_webhook",
    "WebhookEvent",
]
