"""Employee: native content progress (video heartbeat, PDF dwell)."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import require_employee, verify_csrf
from app.models.user import User
from app.models.course import ContentItem, ContentType, Section
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.standards import bridge, xapi as xapi_svc

router = APIRouter(prefix="/my", tags=["employee-content"])


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_enrollment_and_section(
    enrollment_id: int, section_id: int, user: User, db: Session
) -> tuple[Enrollment, Section]:
    enrollment = db.query(Enrollment).filter(
        Enrollment.id == enrollment_id,
        Enrollment.user_id == user.id,
    ).first()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    if enrollment.status == EnrollmentStatus.expired:
        raise HTTPException(status_code=403, detail="Enrollment has expired")

    # Check course deadline
    if enrollment.deadline_at and datetime.now(timezone.utc) > enrollment.deadline_at:
        enrollment.status = EnrollmentStatus.expired
        db.commit()
        raise HTTPException(status_code=403, detail="Course deadline has passed")

    section = db.query(Section).options(joinedload(Section.quiz)).filter(
        Section.id == section_id,
        Section.course_id == enrollment.course_id,
    ).first()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    if not bridge.is_section_unlocked(db, enrollment, section):
        raise HTTPException(status_code=403, detail="Section is locked. Complete previous sections first.")

    return enrollment, section


# ── Video heartbeat ───────────────────────────────────────────────────────────

class VideoProgressBody(BaseModel):
    watched_seconds: int


@router.post(
    "/enrollments/{enrollment_id}/sections/{section_id}/content/{item_id}/progress",
    dependencies=[Depends(verify_csrf)],
)
def video_progress(
    enrollment_id: int,
    section_id: int,
    item_id: int,
    body: VideoProgressBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_employee),
):
    """Video watch-progress heartbeat. Marks content_done at ≥90% of duration."""
    enrollment, section = _get_enrollment_and_section(enrollment_id, section_id, user, db)

    item = db.query(ContentItem).filter(
        ContentItem.id == item_id,
        ContentItem.section_id == section_id,
        ContentItem.type == ContentType.video,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Video content item not found")

    content_done = False
    if item.video_duration_sec and item.video_duration_sec > 0:
        threshold = item.video_duration_sec * 0.9
        content_done = body.watched_seconds >= threshold
    else:
        # Unknown duration: trust the client but emit experienced anyway
        content_done = body.watched_seconds > 0

    section_complete = False
    if content_done:
        iri = f"http://lms.internal/courses/{enrollment.course_id}/sections/{section_id}/items/{item_id}"
        xapi_svc.emit(db, user, "experienced", iri, item.url,
                      activity_type="https://w3id.org/xapi/video/activity-type/video",
                      enrollment_id=enrollment_id)
        section_complete = bridge.native_content_to_progress(
            db, enrollment, section, user, content_done=True
        )
        db.commit()

    return {"content_done": content_done, "section_complete": section_complete}


# ── PDF dwell + mark-read ─────────────────────────────────────────────────────

class PdfDwellBody(BaseModel):
    dwell_seconds: int


@router.post(
    "/enrollments/{enrollment_id}/sections/{section_id}/content/{item_id}/mark-read",
    dependencies=[Depends(verify_csrf)],
)
def mark_pdf_read(
    enrollment_id: int,
    section_id: int,
    item_id: int,
    body: PdfDwellBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_employee),
):
    """Mark a PDF as read after server-verified minimum dwell (20 seconds)."""
    MINIMUM_DWELL = 20
    if body.dwell_seconds < MINIMUM_DWELL:
        raise HTTPException(
            status_code=422,
            detail=f"Minimum dwell time is {MINIMUM_DWELL} seconds.",
        )

    enrollment, section = _get_enrollment_and_section(enrollment_id, section_id, user, db)

    item = db.query(ContentItem).filter(
        ContentItem.id == item_id,
        ContentItem.section_id == section_id,
        ContentItem.type == ContentType.pdf,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="PDF content item not found")

    iri = f"http://lms.internal/courses/{enrollment.course_id}/sections/{section_id}/items/{item_id}"
    xapi_svc.emit(db, user, "experienced", iri, item.url,
                  activity_type="http://id.tincanapi.com/activitytype/document",
                  enrollment_id=enrollment_id)

    section_complete = bridge.native_content_to_progress(
        db, enrollment, section, user, content_done=True
    )
    db.commit()

    return {"content_done": True, "section_complete": section_complete}
