"""
Verifies a LiveKit webhook request and parses it into the small set of
events the rest of the app cares about. Raises on a bad signature; returns
None (caller should just 200 and ignore) for event types we don't model.
"""
from livekit import api as lk_api

from .schemas import WebhookEvent, WebhookParticipant, WebhookTrack

_RELEVANT_EVENTS = {
    "participant_joined", "participant_left", "room_started", "room_finished",
    "track_published", "track_unpublished",
}

# LiveKit's TrackSource enum (protobuf) — mapped to plain strings so callers
# outside this package never need to import livekit-api's proto types.
_TRACK_SOURCE_NAMES = {
    1: "camera",
    2: "microphone",
    3: "screen_share",
    4: "screen_share_audio",
}


def verify_and_parse_webhook(
    body: bytes, auth_header: str, api_key: str, api_secret: str
) -> WebhookEvent | None:
    """
    Raises ValueError (wrapping the SDK's verification error) if the
    signature doesn't check out — callers should turn that into a 401.
    """
    # WebhookReceiver takes a TokenVerifier, not the raw key/secret pair
    # directly (livekit-api==0.8.2) — passing (api_key, api_secret) straight
    # through raises "takes 2 positional arguments but 3 were given".
    token_verifier = lk_api.TokenVerifier(api_key, api_secret)
    receiver = lk_api.WebhookReceiver(token_verifier)
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

    track = None
    if event.event in ("track_published", "track_unpublished") and event.track:
        track = WebhookTrack(source=_TRACK_SOURCE_NAMES.get(event.track.source, "unknown"))

    room_name = event.room.name if event.room else ""
    return WebhookEvent(
        event=event.event,
        room_name=room_name,
        participant=participant,
        track=track,
        raw_event_id=event.id,
    )
