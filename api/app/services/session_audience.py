"""
Resolves who is allowed into a LiveSession: the course's normal CourseTarget
(discipline+level) audience, unioned with any session-specific
SessionAudienceRule rows (see models/live_session.py for why rules are
additive rather than a replacement).
"""
from sqlalchemy import tuple_
from sqlalchemy.orm import Session

from app.models.course import CourseTarget
from app.models.live_session import LiveSession
from app.models.user import User, UserRole


def is_user_in_session_audience(
    db: Session, live_session: LiveSession, course_id: int, user: User
) -> bool:
    if user.discipline_id is not None and user.level_id is not None:
        course_target_match = (
            db.query(CourseTarget)
            .filter(
                CourseTarget.course_id == course_id,
                CourseTarget.discipline_id == user.discipline_id,
                CourseTarget.level_id == user.level_id,
            )
            .first()
            is not None
        )
        if course_target_match:
            return True

    for rule in live_session.audience_rules:
        if rule.user_id is not None and rule.user_id == user.id:
            return True
        if rule.discipline_id is not None and rule.discipline_id == user.discipline_id:
            return True
        if rule.level_id is not None and rule.level_id == user.level_id:
            return True
    return False


def resolve_session_audience_user_ids(
    db: Session, live_session: LiveSession, course_id: int
) -> set[int]:
    """
    Bulk resolution of every eligible active employee id — used by the
    reminder scheduler to decide who to email. The join endpoint does NOT
    use this; it re-checks eligibility per-user via is_user_in_session_audience
    against live DB state at join time, since that's the security boundary.
    """
    ids: set[int] = set()
    base = db.query(User.id).filter(User.active.is_(True), User.role == UserRole.employee)

    course_target_pairs = (
        db.query(CourseTarget.discipline_id, CourseTarget.level_id)
        .filter(CourseTarget.course_id == course_id)
        .all()
    )
    if course_target_pairs:
        matched = base.filter(
            tuple_(User.discipline_id, User.level_id).in_(course_target_pairs)
        ).all()
        ids.update(uid for (uid,) in matched)

    for rule in live_session.audience_rules:
        if rule.user_id is not None:
            ids.add(rule.user_id)
        elif rule.discipline_id is not None:
            matched = base.filter(User.discipline_id == rule.discipline_id).all()
            ids.update(uid for (uid,) in matched)
        elif rule.level_id is not None:
            matched = base.filter(User.level_id == rule.level_id).all()
            ids.update(uid for (uid,) in matched)

    return ids
