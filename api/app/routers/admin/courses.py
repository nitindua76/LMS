from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.dependencies import require_admin, verify_csrf
from app.models.user import User
from app.models.course import Course, CourseStatus, CourseTarget
from app.models.discipline import Discipline
from app.models.level import Level
from app.schemas.common import PaginatedResponse
from app.schemas.course import (
    CourseCreate, CourseUpdate, CourseRead, CourseSummary,
    CourseTargetCreate, CourseTargetRead,
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
    q = db.query(Course)
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
