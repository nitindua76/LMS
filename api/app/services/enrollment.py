"""
Server-side course state computation — the single authoritative function.
M4 and M5 extend this, they do not replace it.
"""
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.course import Course, CourseTarget, CourseStatus
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.user import User
from app.schemas.enrollment import CourseState


def get_assigned_courses(db: Session, user: User) -> List[Course]:
    """Return published courses whose targets match the user's discipline+level."""
    if user.discipline_id is None or user.level_id is None:
        return []
    targets = (
        db.query(CourseTarget)
        .filter(
            CourseTarget.discipline_id == user.discipline_id,
            CourseTarget.level_id == user.level_id,
        )
        .all()
    )
    if not targets:
        return []
    course_ids = {t.course_id for t in targets}
    return (
        db.query(Course)
        .filter(Course.id.in_(course_ids), Course.status == CourseStatus.published)
        .all()
    )


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
