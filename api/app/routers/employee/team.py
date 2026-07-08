from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import require_employee
from app.models.user import User
from app.models.course import Course, Section
from app.models.enrollment import Enrollment, SectionProgress, QuizAttempt, QuizAttemptStatus
from app.schemas.enrollment import CourseState
from app.schemas.controller import TeamMemberSummary, TeamMemberCourseDetail, SectionScore
from app.services.controller import get_direct_reports, is_controller_of
from app.services.enrollment import (
    get_assigned_courses, get_enrollment_map, compute_course_state,
)
from app.services import content_progress

router = APIRouter(prefix="/my/team", tags=["employee-team"])


def _load_subordinate(db: Session, controller: User, subordinate_id: int) -> User:
    if not is_controller_of(db, controller, subordinate_id):
        raise HTTPException(status_code=403, detail="This user is not one of your reports")
    return db.get(User, subordinate_id)


@router.get("", response_model=List[TeamMemberSummary])
def my_team(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employee),
):
    """Employees currently reporting to the caller. Empty list if they control no one."""
    return (
        db.query(User)
        .options(joinedload(User.discipline), joinedload(User.level))
        .filter(User.id.in_([u.id for u in get_direct_reports(db, current_user)] or [-1]))
        .order_by(User.name)
        .all()
    )


@router.get("/{subordinate_id}/courses", response_model=List[CourseState])
def team_member_courses(
    subordinate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employee),
):
    """Read-only course states for a direct report — same computation as /my/courses."""
    subordinate = _load_subordinate(db, current_user, subordinate_id)
    from app.services.enrollment import build_my_courses
    return build_my_courses(db, subordinate)


@router.get("/{subordinate_id}/courses/{course_id}", response_model=TeamMemberCourseDetail)
def team_member_course_detail(
    subordinate_id: int,
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employee),
):
    """
    Read-only progress + scores for one course for a direct report. Deliberately
    omits content URLs/links — the controller reviews outcomes, not the material
    itself, so no signed content URLs are minted for this view.
    """
    subordinate = _load_subordinate(db, current_user, subordinate_id)

    assigned = get_assigned_courses(db, subordinate)
    assigned_ids = {c.id for c in assigned}
    if course_id not in assigned_ids:
        raise HTTPException(status_code=404, detail="Course not found for this employee")

    course = (
        db.query(Course)
        .options(
            joinedload(Course.sections).joinedload(Section.quiz),
            joinedload(Course.sections).joinedload(Section.content_items),
        )
        .filter(Course.id == course_id)
        .first()
    )
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    enrollment_map = get_enrollment_map(db, subordinate.id, [course_id])
    enrollment = enrollment_map.get(course_id)

    from app.models.enrollment import EnrollmentStatus
    mandatory_courses = [c for c in assigned if c.mandatory]
    all_mandatory_done = all(
        enrollment_map.get(c.id) is not None
        and enrollment_map[c.id].status == EnrollmentStatus.completed
        for c in mandatory_courses
    )
    state = compute_course_state(course, enrollment, all_mandatory_done)

    progress_map: dict[int, SectionProgress] = {}
    best_scores: dict[int, tuple[int | None, int]] = {}  # section's quiz_id -> (best_pct, attempts_used)
    content_progress_map: dict = {}
    if enrollment:
        for sp in db.query(SectionProgress).filter(
            SectionProgress.enrollment_id == enrollment.id
        ).all():
            progress_map[sp.section_id] = sp

        all_item_ids = [ci.id for s in course.sections for ci in s.content_items]
        content_progress_map = content_progress.get_progress_map(db, enrollment.id, all_item_ids)

        quiz_ids = [s.quiz.id for s in course.sections if s.quiz is not None]
        if quiz_ids:
            attempts = (
                db.query(QuizAttempt)
                .filter(
                    QuizAttempt.enrollment_id == enrollment.id,
                    QuizAttempt.quiz_id.in_(quiz_ids),
                    QuizAttempt.status == QuizAttemptStatus.submitted,
                )
                .all()
            )
            by_quiz: dict[int, list[QuizAttempt]] = {}
            for a in attempts:
                by_quiz.setdefault(a.quiz_id, []).append(a)
            for quiz_id, quiz_attempts in by_quiz.items():
                best_pct = max((a.score_pct for a in quiz_attempts if a.score_pct is not None), default=None)
                best_scores[quiz_id] = (best_pct, len(quiz_attempts))

    def _content_pct(s: Section) -> Optional[float]:
        sp = progress_map.get(s.id)
        if sp and sp.completed_at:
            return 100.0
        return content_progress.compute_section_native_pct(s, content_progress_map)

    sections_data = [
        SectionScore(
            section_id=s.id,
            title=s.title,
            order_index=s.order_index,
            content_done=(progress_map.get(s.id).content_done if progress_map.get(s.id) else False),
            quiz_passed=(progress_map.get(s.id).quiz_passed if progress_map.get(s.id) else None),
            completed_at=(
                progress_map[s.id].completed_at.isoformat()
                if progress_map.get(s.id) and progress_map[s.id].completed_at else None
            ),
            has_quiz=s.quiz is not None,
            best_score_pct=best_scores.get(s.quiz.id, (None, 0))[0] if s.quiz else None,
            attempts_used=best_scores.get(s.quiz.id, (None, 0))[1] if s.quiz else 0,
            content_pct=_content_pct(s),
        )
        for s in sorted(course.sections, key=lambda x: x.order_index)
    ]

    return TeamMemberCourseDetail(
        id=course.id,
        title=course.title,
        mandatory=course.mandatory,
        state=state.state,
        lock_reason=state.lock_reason,
        deadline_at=state.deadline_at.isoformat() if state.deadline_at else None,
        enrollment_id=enrollment.id if enrollment else None,
        started_at=enrollment.started_at.isoformat() if enrollment and enrollment.started_at else None,
        sections=sections_data,
    )
