"""
Server-side course state computation — the single authoritative function.
M4 and M5 extend this, they do not replace it.
"""
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.course import Course, CourseTarget, CourseTargetUser, CourseStatus, Section, ContentItem
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.live_session import LiveSession, SessionAudienceRule
from app.models.user import User
from app.schemas.enrollment import CourseState


def get_assigned_courses(db: Session, user: User) -> List[Course]:
    """
    Return published courses whose targets match the user's discipline+level,
    plus any course the user is individually added to via CourseTargetUser
    (models/course.py), plus any course where the user is specifically
    invited to a live session via SessionAudienceRule — even if their own
    discipline/level isn't part of the course's normal CourseTarget audience
    (see models/live_session.py).
    """
    course_ids: set[int] = set()

    individually_targeted = db.query(CourseTargetUser.course_id).filter(
        CourseTargetUser.user_id == user.id
    ).all()
    course_ids.update(cid for (cid,) in individually_targeted)

    if user.discipline_id is not None and user.level_id is not None:
        targets = (
            db.query(CourseTarget)
            .filter(
                CourseTarget.discipline_id == user.discipline_id,
                CourseTarget.level_id == user.level_id,
            )
            .all()
        )
        course_ids.update(t.course_id for t in targets)

    rule_conditions = [SessionAudienceRule.user_id == user.id]
    if user.discipline_id is not None:
        rule_conditions.append(SessionAudienceRule.discipline_id == user.discipline_id)
    if user.level_id is not None:
        rule_conditions.append(SessionAudienceRule.level_id == user.level_id)

    invited = (
        db.query(Section.course_id)
        .join(ContentItem, ContentItem.section_id == Section.id)
        .join(LiveSession, LiveSession.content_item_id == ContentItem.id)
        .join(SessionAudienceRule, SessionAudienceRule.live_session_id == LiveSession.id)
        .filter(or_(*rule_conditions))
        .all()
    )
    course_ids.update(cid for (cid,) in invited)

    if not course_ids:
        return []
    return (
        db.query(Course)
        .filter(Course.id.in_(course_ids), Course.status == CourseStatus.published)
        .all()
    )


def enrollment_deadline_passed(enrollment: Enrollment) -> bool:
    """
    True if this enrollment's deadline_at has passed and content access
    should be blocked — except for completed/failed, which are terminal:
    the deadline governs the in-progress window (finish the course by X),
    not review/replay access to an outcome that's already been decided. An
    employee revisiting a completed course's video after its deadline
    timestamp quietly elapsed must not get 403'd or downgraded to expired.
    """
    if enrollment.status in (EnrollmentStatus.completed, EnrollmentStatus.failed):
        return False
    return bool(enrollment.deadline_at and datetime.now(timezone.utc) > enrollment.deadline_at)


def get_enrollment_map(db: Session, user_id: int, course_ids: List[int]) -> dict[int, Enrollment]:
    """Return {course_id: Enrollment} for existing enrollment rows."""
    enrollments = (
        db.query(Enrollment)
        .filter(Enrollment.user_id == user_id, Enrollment.course_id.in_(course_ids))
        .all()
    )
    return {e.course_id: e for e in enrollments}


def compute_course_state(
    course: Course,
    enrollment: Optional[Enrollment],
    all_mandatory_completed: bool,
) -> CourseState:
    """
    Derive the display state for one course card.

    Gate: optional courses are locked until every mandatory course is completed.
    This function is the single source of truth — M4/M5 only add enrollment rows
    and update their status; the state derivation logic lives here.
    """
    if enrollment is not None:
        state = enrollment.status.value
        return CourseState(
            course_id=course.id,
            title=course.title,
            mandatory=course.mandatory,
            duration_days=course.duration_days,
            state=state,
            enrollment_id=enrollment.id,
            deadline_at=enrollment.deadline_at,
        )

    # No enrollment row yet
    if not course.mandatory and not all_mandatory_completed:
        return CourseState(
            course_id=course.id,
            title=course.title,
            mandatory=course.mandatory,
            duration_days=course.duration_days,
            state="locked",
            lock_reason="Complete all mandatory courses to unlock",
        )

    return CourseState(
        course_id=course.id,
        title=course.title,
        mandatory=course.mandatory,
        duration_days=course.duration_days,
        state="not_started",
    )


def build_my_courses(db: Session, user: User) -> List[CourseState]:
    """
    Full pipeline: assigned courses → enrollment map → gate check → states.
    Called by the employee /my/courses endpoint.
    """
    courses = get_assigned_courses(db, user)
    if not courses:
        return []

    course_ids = [c.id for c in courses]
    enrollment_map = get_enrollment_map(db, user.id, course_ids)

    mandatory_courses = [c for c in courses if c.mandatory]
    all_mandatory_completed = all(
        enrollment_map.get(c.id) is not None
        and enrollment_map[c.id].status == EnrollmentStatus.completed
        for c in mandatory_courses
    )

    return [
        compute_course_state(course, enrollment_map.get(course.id), all_mandatory_completed)
        for course in courses
    ]
