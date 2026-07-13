from datetime import datetime, timedelta, timezone

from app.models.course import Course, CourseStatus, CourseTarget, Section, ContentItem, ContentType
from app.models.discipline import Discipline
from app.models.level import Level
from app.models.live_session import LiveSession, SessionAudienceRule, SessionMode, SessionStatus
from app.models.user import User, UserRole
from app.services.session_audience import is_user_in_session_audience, resolve_session_audience_user_ids


def _make_user(db, *, discipline_id=None, level_id=None, email="u@example.com"):
    user = User(
        name="Test User", email=email, password_hash="x",
        discipline_id=discipline_id, level_id=level_id, role=UserRole.employee,
    )
    db.add(user)
    db.flush()
    return user


def _make_course_with_session(db, *, target_discipline_id=None, target_level_id=None):
    course = Course(title="Q3 Town Hall", status=CourseStatus.published)
    db.add(course)
    db.flush()

    if target_discipline_id is not None and target_level_id is not None:
        db.add(CourseTarget(course_id=course.id, discipline_id=target_discipline_id, level_id=target_level_id))

    section = Section(course_id=course.id, order_index=1, title="Live Session")
    db.add(section)
    db.flush()

    item = ContentItem(section_id=section.id, order_index=1, type=ContentType.meeting, url="Town Hall")
    db.add(item)
    db.flush()

    now = datetime.now(timezone.utc)
    live_session = LiveSession(
        content_item_id=item.id, room_name=f"room-{item.id}", mode=SessionMode.meeting,
        status=SessionStatus.scheduled, start_at=now + timedelta(hours=1), end_at=now + timedelta(hours=2),
    )
    db.add(live_session)
    db.flush()
    return course, live_session


def test_course_level_target_match(db):
    disc = Discipline(name="Engineering")
    level = Level(code="L1", name="Junior", rank=1)
    db.add_all([disc, level])
    db.flush()

    course, session = _make_course_with_session(db, target_discipline_id=disc.id, target_level_id=level.id)
    user = _make_user(db, discipline_id=disc.id, level_id=level.id)

    assert is_user_in_session_audience(db, session, course.id, user) is True


def test_unrelated_user_not_in_audience(db):
    disc = Discipline(name="Engineering")
    other_disc = Discipline(name="Sales")
    level = Level(code="L1", name="Junior", rank=1)
    db.add_all([disc, other_disc, level])
    db.flush()

    course, session = _make_course_with_session(db, target_discipline_id=disc.id, target_level_id=level.id)
    user = _make_user(db, discipline_id=other_disc.id, level_id=level.id, email="other@example.com")

    assert is_user_in_session_audience(db, session, course.id, user) is False


def test_session_specific_discipline_rule_grants_access_beyond_course_target(db):
    """A SessionAudienceRule should admit a discipline the course itself
    never targeted — additive, not a subset of CourseTarget."""
    targeted_disc = Discipline(name="Engineering")
    invited_disc = Discipline(name="Sales")
    level = Level(code="L1", name="Junior", rank=1)
    db.add_all([targeted_disc, invited_disc, level])
    db.flush()

    course, session = _make_course_with_session(db, target_discipline_id=targeted_disc.id, target_level_id=level.id)
    db.add(SessionAudienceRule(live_session_id=session.id, discipline_id=invited_disc.id))
    db.flush()

    invited_user = _make_user(db, discipline_id=invited_disc.id, level_id=level.id, email="invited@example.com")
    assert is_user_in_session_audience(db, session, course.id, invited_user) is True


def test_session_specific_user_rule_grants_access(db):
    disc = Discipline(name="Engineering")
    level = Level(code="L1", name="Junior", rank=1)
    db.add_all([disc, level])
    db.flush()

    course, session = _make_course_with_session(db)  # no course-level target at all
    invited_user = _make_user(db, discipline_id=disc.id, level_id=level.id, email="solo@example.com")
    db.add(SessionAudienceRule(live_session_id=session.id, user_id=invited_user.id))
    db.flush()
    db.refresh(session)

    assert is_user_in_session_audience(db, session, course.id, invited_user) is True

    other_user = _make_user(db, discipline_id=disc.id, level_id=level.id, email="not-invited@example.com")
    assert is_user_in_session_audience(db, session, course.id, other_user) is False


def test_resolve_session_audience_user_ids_unions_target_and_rules(db):
    disc = Discipline(name="Engineering")
    level = Level(code="L1", name="Junior", rank=1)
    db.add_all([disc, level])
    db.flush()

    course, session = _make_course_with_session(db, target_discipline_id=disc.id, target_level_id=level.id)
    targeted_user = _make_user(db, discipline_id=disc.id, level_id=level.id, email="targeted@example.com")
    solo_invited = _make_user(db, discipline_id=None, level_id=None, email="solo2@example.com")
    db.add(SessionAudienceRule(live_session_id=session.id, user_id=solo_invited.id))
    db.flush()
    db.refresh(session)

    ids = resolve_session_audience_user_ids(db, session, course.id)
    assert targeted_user.id in ids
    assert solo_invited.id in ids
