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
from app.services import content_progress
from app.services.enrollment import enrollment_deadline_passed

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

    if enrollment_deadline_passed(enrollment):
        enrollment.status = EnrollmentStatus.expired
        db.commit()
        raise HTTPException(status_code=403, detail="Course deadline has passed")

    section = db.query(Section).options(
        joinedload(Section.quiz), joinedload(Section.content_items)
    ).filter(
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
    """
    Video watch-progress heartbeat. Marks this item done at ≥90% of duration.

    The claimed `watched_seconds` is never trusted outright: it's bounded by
    wall-clock time actually elapsed since the last heartbeat (see
    app/services/content_progress.py), so a single POST claiming an enormous
    watched_seconds value can't instantly complete the video. The section
    itself only flips to content_done once every native (video/pdf) item in
    it is individually done — not as soon as this one item is.
    """
    enrollment, section = _get_enrollment_and_section(enrollment_id, section_id, user, db)

    item = db.query(ContentItem).filter(
        ContentItem.id == item_id,
        ContentItem.section_id == section_id,
        ContentItem.type == ContentType.video,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Video content item not found")

    effective_watched = content_progress.record_heartbeat(db, enrollment_id, item_id, body.watched_seconds)
    db.commit()  # persist the bookkeeping row regardless of whether the threshold is met below —
                 # otherwise a not-yet-complete heartbeat never survives, and the next call sees no
                 # history to bound against (see content_progress.py docstring)

    if item.video_duration_sec and item.video_duration_sec > 0:
        threshold = item.video_duration_sec * 0.9
        content_done = effective_watched >= threshold
    else:
        # Unknown duration: no threshold to bound against — trust presence of any watch time
        content_done = effective_watched > 0

    section_complete = False
    if content_done:
        content_progress.mark_done(db, enrollment_id, item_id)
        iri = f"http://lms.internal/courses/{enrollment.course_id}/sections/{section_id}/items/{item_id}"
        xapi_svc.emit(db, user, "experienced", iri, item.url,
                      activity_type="https://w3id.org/xapi/video/activity-type/video",
                      enrollment_id=enrollment_id)
        if content_progress.all_native_items_done(db, enrollment, section):
            section_complete = bridge.native_content_to_progress(
                db, enrollment, section, user, content_done=True
            )
        db.commit()

    return {"content_done": content_done, "section_complete": section_complete}


# ── External/embedded video (e.g. YouTube) — dwell-based mark-watched ─────────
#
# A native <video> element can report real currentTime via the heartbeat above.
# An embedded YouTube iframe cannot (no cross-origin access to its player state
# without wiring up the YouTube IFrame API), so external video links complete
# via a minimum-dwell acknowledgment instead — the same trust model already
# used for PDFs.

class VideoWatchedBody(BaseModel):
    dwell_seconds: int


@router.post(
    "/enrollments/{enrollment_id}/sections/{section_id}/content/{item_id}/mark-watched",
    dependencies=[Depends(verify_csrf)],
)
def mark_video_watched(
    enrollment_id: int,
    section_id: int,
    item_id: int,
    body: VideoWatchedBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_employee),
):
    """Mark an externally-embedded video (no storage_key) as watched after a minimum dwell."""
    enrollment, section = _get_enrollment_and_section(enrollment_id, section_id, user, db)

    item = db.query(ContentItem).filter(
        ContentItem.id == item_id,
        ContentItem.section_id == section_id,
        ContentItem.type == ContentType.video,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Video content item not found")
    if item.storage_key:
        raise HTTPException(
            status_code=422,
            detail="This video is directly playable — use the watch-progress heartbeat instead",
        )

    minimum_dwell = 30
    if item.video_duration_sec and item.video_duration_sec > 0:
        minimum_dwell = min(int(item.video_duration_sec * 0.6), 300)

    effective_dwell = content_progress.record_dwell(db, enrollment_id, item_id, body.dwell_seconds)
    db.commit()  # persist first_seen_at/last_heartbeat_at even on rejection — see content_progress.py
    if effective_dwell < minimum_dwell:
        raise HTTPException(
            status_code=422,
            detail=f"Minimum watch time is {minimum_dwell} seconds.",
        )

    content_progress.mark_done(db, enrollment_id, item_id)
    iri = f"http://lms.internal/courses/{enrollment.course_id}/sections/{section_id}/items/{item_id}"
    xapi_svc.emit(db, user, "experienced", iri, item.url,
                  activity_type="https://w3id.org/xapi/video/activity-type/video",
                  enrollment_id=enrollment_id)

    section_complete = False
    if content_progress.all_native_items_done(db, enrollment, section):
        section_complete = bridge.native_content_to_progress(
            db, enrollment, section, user, content_done=True
        )
    db.commit()

    return {"content_done": True, "section_complete": section_complete}


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

    enrollment, section = _get_enrollment_and_section(enrollment_id, section_id, user, db)

    item = db.query(ContentItem).filter(
        ContentItem.id == item_id,
        ContentItem.section_id == section_id,
        ContentItem.type == ContentType.pdf,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="PDF content item not found")

    effective_dwell = content_progress.record_dwell(db, enrollment_id, item_id, body.dwell_seconds)
    db.commit()  # persist first_seen_at/last_heartbeat_at even on rejection — see content_progress.py
    if effective_dwell < MINIMUM_DWELL:
        raise HTTPException(
            status_code=422,
            detail=f"Minimum dwell time is {MINIMUM_DWELL} seconds.",
        )

    content_progress.mark_done(db, enrollment_id, item_id)
    iri = f"http://lms.internal/courses/{enrollment.course_id}/sections/{section_id}/items/{item_id}"
    xapi_svc.emit(db, user, "experienced", iri, item.url,
                  activity_type="http://id.tincanapi.com/activitytype/document",
                  enrollment_id=enrollment_id)

    section_complete = False
    if content_progress.all_native_items_done(db, enrollment, section):
        section_complete = bridge.native_content_to_progress(
            db, enrollment, section, user, content_done=True
        )
    db.commit()

    return {"content_done": True, "section_complete": section_complete}
