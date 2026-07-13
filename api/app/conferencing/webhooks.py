"""
Verifies a LiveKit webhook request and parses it into the small set of
events the rest of the app cares about. Raises on a bad signature; returns
None (caller should just 200 and ignore) for event types we don't model.
"""
from livekit import api as lk_api

from .schemas import WebhookEvent, WebhookParticipant

_RELEVANT_EVENTS = {"participant_joined", "participant_left", "room_started", "room_finished"}


def verify_and_parse_webhook(
    body: bytes, auth_header: str, api_key: str, api_secret: str
) -> WebhookEvent | None:
    """
    Raises ValueError (wrapping the SDK's verification error) if the
    signature doesn't check out — callers should turn that into a 401.
    """
    receiver = lk_api.WebhookReceiver(api_key, api_secret)
    try:
        event = receiver.receive(body.decode("utf-8"), auth_header)
    except Exception as exc:  # SDK raises its own error type on bad signature
        raise ValueError(f"Invalid LiveKit webhook signature: {exc}") from exc

    if event.event not in _RELEVANT_EVENTS:
        return None

    participant = None
    if event.participant and event.participant.identity:
        participant = WebhookParticipant(
            identity=event.participant.identity,
            name=event.participant.name or None,
        )

    room_name = event.room.name if event.room else ""
    return WebhookEvent(
        event=event.event,
        room_name=room_name,
        participant=participant,
        raw_event_id=event.id,
    )
