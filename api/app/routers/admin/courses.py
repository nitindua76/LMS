import csv
import io
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.dependencies import require_admin, verify_csrf
from app.models.user import User
from app.models.course import Course, CourseStatus, CourseTarget, CourseTargetUser, Section, ContentItem
from app.models.discipline import Discipline
from app.models.level import Level
from app.schemas.common import PaginatedResponse
from app.schemas.course import (
    CourseCreate, CourseUpdate, CourseRead, CourseSummary,
    CourseTargetCreate, CourseTargetRead,
    CourseTargetUserCreate, CourseTargetUserRead, CsvImportRowResult,
    CoursePurgeRequest, CoursePurgeResponse,
)
from app.services.audit import audit

router = APIRouter(prefix="/admin/courses", tags=["admin-courses"])


def _load_course(db: Session, course_id: int) -> Course:
    course = (
        db.query(Course)
        .options(joinedload(Course.targets))
        .filter(Course.id == course_id)
        .first()
    )
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.get("", response_model=PaginatedResponse[CourseSummary])
def list_courses(
    page: int = 1,
    page_size: int = 20,
    status: Optional[CourseStatus] = Query(None),
    mandatory: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    q = db.query(Course).options(joinedload(Course.targets))
    if status is not None:
        q = q.filter(Course.status == status)
    if mandatory is not None:
        q = q.filter(Course.mandatory == mandatory)
    total = q.count()
    items = q.order_by(Course.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=CourseRead, status_code=201, dependencies=[Depends(verify_csrf)])
def create_course(
    body: CourseCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    course = Course(**body.model_dump())
    db.add(course)
    db.flush()
    audit(db, actor_id=actor.id, action="create_course", target_type="course",
          target_id=course.id, detail={"title": course.title})
    db.commit()
    return _load_course(db, course.id)


@router.get("/{course_id}", response_model=CourseRead)
def get_course(
    course_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return _load_course(db, course_id)


@router.put("/{course_id}", response_model=CourseRead, dependencies=[Depends(verify_csrf)])
def update_course(
    course_id: int,
    body: CourseUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    course = _load_course(db, course_id)
    if body.status == CourseStatus.published and course.status != CourseStatus.published:
        raise HTTPException(
            status_code=422,
            detail="Use POST /admin/courses/{course_id}/publish to go live — it validates readiness first",
        )
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(course, field, value)
    db.flush()
    audit(db, actor_id=actor.id, action="update_course", target_type="course",
          target_id=course_id)
    db.commit()
    return _load_course(db, course_id)


@router.delete("/{course_id}", status_code=204, dependencies=[Depends(verify_csrf)])
def archive_course(
    course_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    """Soft delete — sets status to archived."""
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    course.status = CourseStatus.archived
    audit(db, actor_id=actor.id, action="archive_course", target_type="course", target_id=course_id)
    db.commit()


@router.delete(
    "/{course_id}/purge",
    response_model=CoursePurgeResponse,
    dependencies=[Depends(verify_csrf)],
)
def purge_course(
    course_id: int,
    body: CoursePurgeRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    """
    Permanently delete a course and everything under it — sections, content,
    quizzes/questions, targets, enrollments, section/content progress, quiz
    attempts. This is irreversible and destroys real completion history if any
    exists; it exists to clean up test/throwaway courses, not to retire real
    ones (use archive for that).

    Two safety gates: the course must already be off draft/archived (never
    currently published — publish it away first if it's live), and the caller
    must echo the exact course title back, so this can't be fired by a stray
    click or a copy-pasted curl command without deliberately re-reading what
    it's about to destroy.

    Deletion order matters because of RESTRICT foreign keys: QuizAttempt
    restricts Enrollment, and Enrollment restricts Course. Deleting attempts
    then enrollments first lets everything else (SectionProgress,
    ContentProgress, SentReminder — all CASCADE from enrollment_id) go with
    them, and only then does deleting the course cascade cleanly through
    sections/content/quizzes/targets.
    """
    from app.models.enrollment import Enrollment, QuizAttempt

    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    if course.status == CourseStatus.published:
        raise HTTPException(
            status_code=422,
            detail="Cannot purge a published course — archive it first",
        )

    if body.confirm_title != course.title:
        raise HTTPException(
            status_code=422,
            detail="confirm_title must exactly match the course title",
        )

    title = course.title
    enrollment_ids = [
        row[0] for row in db.query(Enrollment.id).filter(Enrollment.course_id == course_id).all()
    ]

    attempts_deleted = 0
    if enrollment_ids:
        attempts_deleted = db.query(QuizAttempt).filter(
            QuizAttempt.enrollment_id.in_(enrollment_ids)
        ).delete(synchronize_session=False)

    enrollments_deleted = 0
    if enrollment_ids:
        enrollments_deleted = db.query(Enrollment).filter(
            Enrollment.id.in_(enrollment_ids)
        ).delete(synchronize_session=False)

    audit(
        db, actor_id=actor.id, action="purge_course", target_type="course", target_id=course_id,
        detail={"title": title, "enrollments_deleted": enrollments_deleted, "quiz_attempts_deleted": attempts_deleted},
    )

    db.delete(course)
    db.commit()

    return CoursePurgeResponse(
        course_id=course_id,
        title=title,
        enrollments_deleted=enrollments_deleted,
        quiz_attempts_deleted=attempts_deleted,
    )


# ── Publish gate ─────────────────────────────────────────────────────────────
#
# Course creation only ever produces a draft; going live is a single explicit
# action, gated by a real readiness check rather than the free-form status
# dropdown that used to let an empty, untargeted course go "published".

def _has_live_session_audience(db: Session, course_id: int) -> bool:
    """
    True if any meeting content item in this course already has its own
    session-specific audience (SessionAudienceRule) configured. Lets a
    course whose content is a targeted live session publish without also
    requiring redundant course-level discipline+level targets — an admin
    who already picked attendees on the session itself shouldn't have to
    repeat that in Targeting & Publish.
    """
    from app.models.live_session import LiveSession, SessionAudienceRule

    return (
        db.query(SessionAudienceRule)
        .join(LiveSession, LiveSession.id == SessionAudienceRule.live_session_id)
        .join(ContentItem, ContentItem.id == LiveSession.content_item_id)
        .join(Section, Section.id == ContentItem.section_id)
        .filter(Section.course_id == course_id)
        .first()
        is not None
    )


def _publish_issues(db: Session, course: Course) -> List[str]:
    issues: List[str] = []
    sections = (
        db.query(Section)
        .options(joinedload(Section.content_items), joinedload(Section.quiz))
        .filter(Section.course_id == course.id)
        .order_by(Section.order_index)
        .all()
    )
    if not sections:
        issues.append("Add at least one section")
    for s in sections:
        if not s.content_items and not s.quiz:
            issues.append(f"Section \"{s.title}\" has no content and no quiz")
    has_individual_users = db.query(CourseTargetUser).filter(
        CourseTargetUser.course_id == course.id
    ).first() is not None
    if not course.targets and not has_individual_users and not _has_live_session_audience(db, course.id):
        issues.append(
            "Assign at least one target audience (discipline + level), "
            "add specific employees, or add specific attendees to a live session"
        )
    return issues


@router.get("/{course_id}/publish-readiness")
def publish_readiness(
    course_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    course = _load_course(db, course_id)
    issues = _publish_issues(db, course)
    return {"ready": len(issues) == 0, "issues": issues}


@router.post("/{course_id}/publish", response_model=CourseRead, dependencies=[Depends(verify_csrf)])
def publish_course(
    course_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    course = _load_course(db, course_id)
    issues = _publish_issues(db, course)
    if issues:
        raise HTTPException(status_code=422, detail="Not ready to publish: " + "; ".join(issues))
    course.status = CourseStatus.published
    db.flush()
    audit(db, actor_id=actor.id, action="publish_course", target_type="course", target_id=course_id)
    db.commit()
    return _load_course(db, course_id)


@router.post("/{course_id}/unpublish", response_model=CourseRead, dependencies=[Depends(verify_csrf)])
def unpublish_course(
    course_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    """Pull a published course back to draft — no validation needed to go this direction."""
    course = _load_course(db, course_id)
    course.status = CourseStatus.draft
    db.flush()
    audit(db, actor_id=actor.id, action="unpublish_course", target_type="course", target_id=course_id)
    db.commit()
    return _load_course(db, course_id)


# ── Course targets ─────────────────────────────────────────────────────────────

@router.get("/{course_id}/targets", response_model=List[CourseTargetRead])
def list_targets(
    course_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    _load_course(db, course_id)
    targets = db.query(CourseTarget).filter(CourseTarget.course_id == course_id).all()
    return targets


@router.post("/{course_id}/targets", response_model=CourseTargetRead,
             status_code=201, dependencies=[Depends(verify_csrf)])
def add_target(
    course_id: int,
    body: CourseTargetCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    _load_course(db, course_id)
    if not db.get(Discipline, body.discipline_id):
        raise HTTPException(status_code=422, detail="Discipline not found")
    if not db.get(Level, body.level_id):
        raise HTTPException(status_code=422, detail="Level not found")

    target = CourseTarget(
        course_id=course_id,
        discipline_id=body.discipline_id,
        level_id=body.level_id,
    )
    db.add(target)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This discipline+level target already exists")
    audit(db, actor_id=actor.id, action="add_course_target", target_type="course_target",
          target_id=target.id, detail={"course_id": course_id})
    db.commit()
    db.refresh(target)
    return target


@router.delete("/{course_id}/targets/{target_id}", status_code=204,
               dependencies=[Depends(verify_csrf)])
def remove_target(
    course_id: int,
    target_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    target = db.query(CourseTarget).filter(
        CourseTarget.id == target_id,
        CourseTarget.course_id == course_id,
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    db.delete(target)
    audit(db, actor_id=actor.id, action="remove_course_target", target_type="course_target",
          target_id=target_id, detail={"course_id": course_id})
    db.commit()


# ── Individually-targeted employees ──────────────────────────────────────────
#
# Additive on top of the discipline+level targets above — the same "add
# specific people regardless of their department/level" shape already built
# for live sessions (SessionAudienceRule.user_id), but at the whole-course
# level. See services/enrollment.py::get_assigned_courses for how this
# feeds into what shows up in an employee's My Courses.

def _target_user_read(row: CourseTargetUser) -> CourseTargetUserRead:
    return CourseTargetUserRead(id=row.id, user_id=row.user_id, name=row.user.name, email=row.user.email)


@router.get("/{course_id}/target-users", response_model=List[CourseTargetUserRead])
def list_target_users(
    course_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    _load_course(db, course_id)
    rows = (
        db.query(CourseTargetUser)
        .options(joinedload(CourseTargetUser.user))
        .filter(CourseTargetUser.course_id == course_id)
        .all()
    )
    return [_target_user_read(r) for r in rows]


@router.post("/{course_id}/target-users", response_model=CourseTargetUserRead, status_code=201,
             dependencies=[Depends(verify_csrf)])
def add_target_user(
    course_id: int,
    body: CourseTargetUserCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    _load_course(db, course_id)
    user = db.get(User, body.user_id)
    if not user:
        raise HTTPException(status_code=422, detail="User not found")

    row = CourseTargetUser(course_id=course_id, user_id=body.user_id)
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This employee is already individually targeted")
    audit(db, actor_id=actor.id, action="add_course_target_user", target_type="course_target_user",
          target_id=row.id, detail={"course_id": course_id, "user_id": body.user_id})
    db.commit()
    db.refresh(row)
    return _target_user_read(row)


@router.delete("/{course_id}/target-users/{target_user_id}", status_code=204,
                dependencies=[Depends(verify_csrf)])
def remove_target_user(
    course_id: int,
    target_user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    row = db.query(CourseTargetUser).filter(
        CourseTargetUser.id == target_user_id,
        CourseTargetUser.course_id == course_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(row)
    audit(db, actor_id=actor.id, action="remove_course_target_user", target_type="course_target_user",
          target_id=target_user_id, detail={"course_id": course_id})
    db.commit()


@router.post("/{course_id}/target-users/import", response_model=List[CsvImportRowResult],
             dependencies=[Depends(verify_csrf)])
async def import_target_users_csv(
    course_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    """
    CSV with a single required `email` column — one row per employee to add
    to this course's individual targeting. Same shape/behavior as the
    existing user-import endpoint (admin/users.py): every row is processed,
    good or bad, and reported back rather than aborting on the first error.
    """
    _load_course(db, course_id)
    content = await file.read()
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames or "email" not in {f.strip().lower() for f in reader.fieldnames}:
        raise HTTPException(status_code=422, detail="CSV must have an 'email' column")

    results: List[CsvImportRowResult] = []
    added_count = 0
    for idx, row in enumerate(reader, start=2):
        email = (row.get("email") or row.get("Email") or "").strip().lower()
        if not email:
            results.append(CsvImportRowResult(row=idx, email="", status="error", error="email is required"))
            continue

        user = db.query(User).filter(User.email == email).first()
        if not user:
            results.append(CsvImportRowResult(row=idx, email=email, status="error", error="No user with this email"))
            continue

        existing = db.query(CourseTargetUser).filter(
            CourseTargetUser.course_id == course_id, CourseTargetUser.user_id == user.id,
        ).first()
        if existing:
            results.append(CsvImportRowResult(row=idx, email=email, status="error", error="Already targeted"))
            continue

        target_row = CourseTargetUser(course_id=course_id, user_id=user.id)
        db.add(target_row)
        try:
            db.flush()
            added_count += 1
            results.append(CsvImportRowResult(row=idx, email=email, status="added"))
        except IntegrityError:
            db.rollback()
            results.append(CsvImportRowResult(row=idx, email=email, status="error", error="Concurrent conflict"))

    audit(db, actor_id=actor.id, action="csv_import_course_target_users", target_type="course",
          target_id=course_id, detail={"added_count": added_count})
    db.commit()
    return results
