"""
LiveKit participant identities encode the LMS user id so the webhook adapter
can resolve `LiveSessionParticipant` rows back to a `User` without LiveKit
knowing anything about our data model.
"""

_PREFIX = "user-"


def make_identity(user_id: int) -> str:
    return f"{_PREFIX}{user_id}"


def parse_identity(identity: str) -> int | None:
    if not identity.startswith(_PREFIX):
        return None
    try:
        return int(identity[len(_PREFIX):])
    except ValueError:
        return None
