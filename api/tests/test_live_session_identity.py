from app.services.live_session_identity import make_identity, parse_identity


def test_roundtrip():
    assert parse_identity(make_identity(42)) == 42


def test_parse_rejects_foreign_identity():
    """A LiveKit identity that didn't come from make_identity() (e.g. a bot,
    or a future non-LMS integration) must not be silently coerced into a
    user id — the webhook adapter relies on None meaning 'not one of ours'."""
    assert parse_identity("recorder-bot") is None
    assert parse_identity("") is None


def test_parse_rejects_non_numeric_suffix():
    assert parse_identity("user-abc") is None
