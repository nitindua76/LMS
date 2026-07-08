from datetime import datetime, timezone, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import require_employee, verify_csrf
from app.models.user import User
from app.models.course import Course, Section, Quiz, ContentType
from app.models.enrollment import Enrollment, EnrollmentStatus, SectionProgress
from app.schemas.enrollment import CourseState
from app.schemas.section import SectionRead
from app.services.enrollment import build_my_courses
from app.services import content_progress
from app.standards import bridge, xapi as xapi_svc

router = APIRouter(prefix="/my", tags=["employee"])


@router.get("/courses", response_model=List[CourseState])
def my_courses(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employee),
):
    return build_my_courses(db, current_user)


@router.get("/courses/{course_id}", response_model=dict)
def course_detail(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employee),
):
    """
    Read-only course detail for employees.
    Verifies assignment before serving — employees can only view their assigned courses.
    Content access gate (section locking) is M4.
    """
    from app.services.enrollment import get_assigned_courses, get_enrollment_map, compute_course_state

    assigned = get_assigned_courses(db, current_user)
    assigned_ids = {c.id for c in assigned}
    if course_id not in assigned_ids:
        raise HTTPException(status_code=403, detail="This course is not assigned to you")

    course = (
        db.query(Course)
        .options(
            joinedload(Course.sections).joinedload(Section.content_items),
            joinedload(Course.sections).joinedload(Section.quiz),
        )
        .filter(Course.id == course_id)
        .first()
    )
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    enrollment_map = get_enrollment_map(db, current_user.id, [course_id])
    from app.models.enrollment import EnrollmentStatus
    mandatory_courses = [c for c in assigned if c.mandatory]
    all_mandatory_done = all(
        enrollment_map.get(c.id) is not None
        and enrollment_map[c.id].status == EnrollmentStatus.completed
        for c in mandatory_courses
    )
    state = compute_course_state(course, enrollment_map.get(course_id), all_mandatory_done)

    enrollment = enrollment_map.get(course_id)

    # Compute section lock status if enrolled
    progress_map: dict = {}
    content_progress_map: dict = {}
    if enrollment:
        for sp in db.query(SectionProgress).filter(
            SectionProgress.enrollment_id == enrollment.id
        ).all():
            progress_map[sp.section_id] = sp
        all_item_ids = [ci.id for s in course.sections for ci in s.content_items]
        content_progress_map = content_progress.get_progress_map(db, enrollment.id, all_item_ids)

    sections_data = []
    for s in sorted(course.sections, key=lambda x: x.order_index):
        sp = progress_map.get(s.id)
        locked = enrollment is None or not bridge.is_section_unlocked(db, enrollment, s) if enrollment else True

        # Build signed content URLs — only sign when the section is unlocked
        content_items = []
        for ci in sorted(s.content_items, key=lambda x: x.order_index):
            item_data: dict = {
                "id": ci.id,
                "order_index": ci.order_index,
                "type": ci.type.value,
                "title": ci.url,   # display label, never the storage key
                "video_duration_sec": ci.video_duration_sec,
            }
            if ci.type == ContentType.video:
                cp = content_progress_map.get(ci.id)
                item_data["resume_seconds"] = cp.max_watched_seconds if cp else 0
            if not locked and ci.type == ContentType.scorm:
                # Generate SCORM launch URL on-the-fly
                try:
                    from app.models.package import LearningPackage, PackageFormat
                    from app.services.scorm.token import create_scorm_token
                    from app.config import settings
                    pkg = db.query(LearningPackage).filter(
                        LearningPackage.content_item_id == ci.id,
                        LearningPackage.format == PackageFormat.scorm_2004,
                    ).first()
                    if pkg:
                        token = create_scorm_token(current_user.id, pkg.id, enrollment.id, ttl=7200)
                        mastery_str = f"&mastery={pkg.mastery_score}" if pkg.mastery_score is not None else ""
                        item_data["url"] = (
                            f"{settings.CONTENT_ORIGIN}/loader"
                            f"?pkg={pkg.id}&ci={ci.id}&sco={pkg.launch_href}&token={token}"
                            f"&api={settings.API_EXTERNAL_URL}"
                            f"{mastery_str}"
                        )
                except Exception:
                    pass
            elif not locked and ci.storage_key:
                # Storage-backed content: generate a fresh, expiring signed URL.
                # We do NOT fall back to the raw key on failure — if signing fails the
                # client gets no URL, which is the correct secure default.
                try:
                    from app.services import storage as store
                    item_data["url"] = store.signed_url(ci.storage_key, expires=900)
                except Exception:
                    pass  # url intentionally omitted; client should show "content unavailable"
            elif ci.url.startswith("http"):
                # External content (e.g. a public YouTube/Vimeo link): serve as-is.
                # This is safe because the URL is already public — it's not a storage key.
                item_data["url"] = ci.url
            # else: ci.url is not an http URL and no storage_key — misconfigured item, omit url
            content_items.append(item_data)

        has_started = sp is not None
        scorm_pct: float | None = None

        # Fetch SCORM details if section has SCORM content
        from app.models.package import LearningPackage, ScormCmiData
        scorm_item = next((ci for ci in s.content_items if ci.type == ContentType.scorm), None)
        if scorm_item:
            pkg = db.query(LearningPackage).filter(
                LearningPackage.content_item_id == scorm_item.id
            ).first()
            if pkg:
                cmi_rows = db.query(ScormCmiData).filter(
                    ScormCmiData.user_id == current_user.id,
                    ScormCmiData.learning_package_id == pkg.id,
                ).all()
                if cmi_rows:
                    has_started = True
                    # Only compute partial progress if not fully complete
                    if not (sp and sp.completed_at):
                        vals = []
                        for r in cmi_rows:
                            if r.progress_measure is not None:
                                vals.append(r.progress_measure)
                            elif r.score_scaled is not None:
                                vals.append(r.score_scaled)
                            elif r.completion_status == "completed":
                                vals.append(1.0)
                        if vals:
                            scorm_pct = round(sum(vals) / len(vals) * 100, 1)
        elif any(ci.id in content_progress_map for ci in s.content_items):
            # No SectionProgress row yet doesn't mean untouched — a partially-watched
            # video already has a ContentProgress row before the section is ever
            # marked content_done, so has_started/percentage need to read from there too.
            has_started = True
            if not (sp and sp.completed_at):
                native_pct = content_progress.compute_section_native_pct(s, content_progress_map)
                if native_pct is not None:
                    scorm_pct = native_pct

        # If section is fully complete, show 100%
        if sp and sp.completed_at:
            scorm_pct = 100.0

        sections_data.append({
            "id": s.id,
            "order_index": s.order_index,
            "title": s.title,
            "locked": locked,
            "content_done": (sp.content_done if sp else False) or len(s.content_items) == 0,
            "quiz_passed": sp.quiz_passed if sp else None,
            "completed_at": sp.completed_at.isoformat() if sp and sp.completed_at else None,
            "has_quiz": s.quiz is not None,
            "has_started": has_started,
            "scorm_pct": scorm_pct,
            "content_items": content_items,
        })

    return {
        "id": course.id,
        "title": course.title,
        "description": course.description,
        "intro": course.intro,
        "duration_days": course.duration_days,
        "mandatory": course.mandatory,
        "state": state.state,
        "lock_reason": state.lock_reason,
        "deadline_at": state.deadline_at.isoformat() if state.deadline_at else None,
        "enrollment_id": enrollment.id if enrollment else None,
        "sections": sections_data,
    }


class _EmptyBody(BaseModel):
    pass


@router.post("/courses/{course_id}/start", dependencies=[Depends(verify_csrf)])
def start_course(
    course_id: int,
    _body: _EmptyBody,    # forces Content-Type: application/json → non-simple request → preflight required
    db: Session = Depends(get_db),
    current_user: User = Depends(require_employee),
):
    """Create enrollment with deadline; idempotent if already enrolled."""
    from app.services.enrollment import get_assigned_courses, get_enrollment_map

    assigned = get_assigned_courses(db, current_user)
    if course_id not in {c.id for c in assigned}:
        raise HTTPException(status_code=403, detail="This course is not assigned to you")

    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")

    existing = db.query(Enrollment).filter(
        Enrollment.user_id == current_user.id,
        Enrollment.course_id == course_id,
    ).first()
    if existing:
        return {"enrollment_id": existing.id, "status": existing.status.value}

    now = datetime.now(timezone.utc)
    deadline = now + timedelta(days=course.duration_days) if course.duration_days else None

    enrollment = Enrollment(
        user_id=current_user.id,
        course_id=course_id,
        status=EnrollmentStatus.in_progress,
        started_at=now,
        deadline_at=deadline,
    )
    db.add(enrollment)
    db.flush()

    iri = f"http://lms.internal/courses/{course_id}"
    xapi_svc.emit(
        db, current_user, "launched", iri, course.title,
        activity_type="http://adlnet.gov/expapi/activities/course",
        enrollment_id=enrollment.id,
    )
    db.commit()

    return {
        "enrollment_id": enrollment.id,
        "status": enrollment.status.value,
        "deadline_at": deadline.isoformat() if deadline else None,
    }
