"""
SCORM 2004 employee launch + run-time endpoints.

launch_router  — employee-facing:  POST /my/enrollments/…/scorm/launch
router         — content-origin-facing: /api/scorm/sessions (runtime CMI calls)

The runtime endpoints are called cross-origin from loader.html using
X-SCORM-Token (not the httpOnly session cookie), so package JS never
touches user credentials.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Header, HTTPException
from fastapi.params import Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.package import LearningPackage, PackageFormat, ScormCmiData
from app.models.enrollment import Enrollment
from app.models.course import Section, ContentItem, ContentType
from app.dependencies import require_employee, verify_csrf
from app.services.scorm.token import create_scorm_token, decode_scorm_token
from app.standards import bridge, xapi as xapi_svc
from app.models.user import User
from app.config import settings

router = APIRouter(prefix="/api/scorm", tags=["scorm-runtime"])

# ── Employee launch ───────────────────────────────────────────────────────────
#
# Mirrors cmi5_launch exactly:
#   • same enrollment-ownership + deadline check
#   • same bridge.is_section_unlocked gate
#   • same 7 200-second (120-minute) token window
#
# The key difference from cmi5 is intentional: cmi5 uses a one-time DB
# session (AU calls /fetch once to consume the token).  SCORM keeps the
# JWT valid for all runtime calls (Initialize/Commit/Terminate) because
# the loader needs it repeatedly throughout the session.

launch_router = APIRouter(tags=["employee-scorm"])

_SCORM_TOKEN_TTL = 60 * 120  # 7 200 s — matches cmi5 SESSION_TTL_MINUTES=120


@launch_router.post(
    "/my/enrollments/{enrollment_id}/sections/{section_id}/scorm/launch",
    dependencies=[Depends(verify_csrf)],
)
def scorm_launch(
    enrollment_id: int,
    section_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_employee),
):
    """
    Issue a short-lived SCORM token and return the loader URL.

    The token is scoped to (user, package, enrollment) — the same triple
    _auth() in the runtime verifies on every CMI call.  The `ci` param in
    the loader URL is the ContentItem.id, which is the key prefix the
    storage layer used when it extracted the package; the nginx alias in
    the content server maps /pkg/{ci}/… to that storage prefix.
    """
    enrollment = db.query(Enrollment).filter(
        Enrollment.id == enrollment_id,
        Enrollment.user_id == user.id,
    ).first()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    if enrollment.deadline_at and datetime.now(timezone.utc) > enrollment.deadline_at:
        raise HTTPException(status_code=403, detail="Course deadline has passed")

    section = db.query(Section).filter(
        Section.id == section_id,
        Section.course_id == enrollment.course_id,
    ).first()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    if not bridge.is_section_unlocked(db, enrollment, section):
        raise HTTPException(status_code=403, detail="Section is locked")

    item = db.query(ContentItem).filter(
        ContentItem.section_id == section_id,
        ContentItem.type == ContentType.scorm,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="No SCORM content in this section")

    pkg = db.query(LearningPackage).filter(
        LearningPackage.content_item_id == item.id,
        LearningPackage.format == PackageFormat.scorm_2004,
    ).first()
    if not pkg:
        raise HTTPException(status_code=404, detail="SCORM package not imported yet")

    token = create_scorm_token(user.id, pkg.id, enrollment.id, ttl=_SCORM_TOKEN_TTL)

    iri = f"http://lms.internal/courses/{enrollment.course_id}/packages/{pkg.id}"
    xapi_svc.emit(db, user, "launched", iri, pkg.title,
                  activity_type="http://adlnet.gov/expapi/activities/lesson",
                  enrollment_id=enrollment_id)
    db.commit()

    loader_url = (
        f"{settings.CONTENT_ORIGIN}/loader"
        f"?pkg={pkg.id}&ci={item.id}&sco={pkg.launch_href}&token={token}"
        f"&api={settings.API_EXTERNAL_URL}"
    )

    return {
        "launch_url":      loader_url,
        "package_id":      pkg.id,
        "content_item_id": item.id,
        "launch_href":     pkg.launch_href,
        "mastery_score":   pkg.mastery_score,
    }


@launch_router.get(
    "/my/enrollments/{enrollment_id}/packages/{package_id}/progress",
)
def get_package_progress(
    enrollment_id: int,
    package_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_employee),
):
    """Retrieve CMI progress (status and scores) for all SCOs in this package."""
    # Verify enrollment ownership
    enrollment = db.query(Enrollment).filter(
        Enrollment.id == enrollment_id,
        Enrollment.user_id == user.id,
    ).first()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    cmi_rows = db.query(ScormCmiData).filter(
        ScormCmiData.user_id == user.id,
        ScormCmiData.learning_package_id == package_id,
    ).all()

    return {
        row.sco_identifier: {
            "completion_status": row.completion_status,
            "success_status": row.success_status,
            "score_scaled": row.score_scaled,
            "score_raw": row.score_raw,
        }
        for row in cmi_rows
    }


class ResetScoBody(BaseModel):
    sco_identifier: str


@launch_router.post(
    "/my/enrollments/{enrollment_id}/packages/{package_id}/sco/reset",
)
def reset_sco_progress(
    enrollment_id: int,
    package_id: int,
    body: ResetScoBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_employee),
):
    """Reset progress for a specific SCO (e.g. to retake a quiz)."""
    # Verify enrollment ownership
    enrollment = db.query(Enrollment).filter(
        Enrollment.id == enrollment_id,
        Enrollment.user_id == user.id,
    ).first()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    # Delete the CMI data row
    db.query(ScormCmiData).filter(
        ScormCmiData.user_id == user.id,
        ScormCmiData.learning_package_id == package_id,
        ScormCmiData.sco_identifier == body.sco_identifier,
    ).delete()

    # Also reset the SectionProgress if it was completed
    from app.models.course import ContentItem, Section
    from app.models.enrollment import SectionProgress
    pkg = db.query(LearningPackage).filter(LearningPackage.id == package_id).first()
    if pkg:
        content_item = db.query(ContentItem).filter(ContentItem.id == pkg.content_item_id).first()
        if content_item:
            sp = db.query(SectionProgress).filter(
                SectionProgress.enrollment_id == enrollment.id,
                SectionProgress.section_id == content_item.section_id,
            ).first()
            if sp:
                sp.content_done = False
                sp.quiz_passed = False
                sp.completed_at = None

    db.commit()
    return {"ok": True}


# ── Token auth dependency ─────────────────────────────────────────────────────

def _auth(
    x_scorm_token: Optional[str] = Header(None, alias="X-SCORM-Token"),
    db: Session = Depends(get_db),
) -> tuple[User, LearningPackage, Enrollment]:
    if not x_scorm_token:
        raise HTTPException(status_code=401, detail="Missing X-SCORM-Token")
    try:
        payload = decode_scorm_token(x_scorm_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired SCORM token")

    user = db.get(User, int(payload["sub"]))
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="User not found or deactivated")

    pkg = db.get(LearningPackage, payload["pkg"])
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")

    enrollment = db.get(Enrollment, payload["enr"])
    if not enrollment or enrollment.user_id != user.id:
        raise HTTPException(status_code=403, detail="Enrollment mismatch")

    # Check deadline
    if enrollment.deadline_at and datetime.now(timezone.utc) > enrollment.deadline_at:
        raise HTTPException(status_code=403, detail="Course deadline has passed")

    return user, pkg, enrollment


# ── Data model helpers ────────────────────────────────────────────────────────

def _cmi_to_dict(cmi: ScormCmiData) -> dict:
    """Flatten ScormCmiData row into the cmi.* key map the SCO expects."""
    d: dict = {}
    if cmi.completion_status:
        d["cmi.completion_status"] = cmi.completion_status
    if cmi.success_status:
        d["cmi.success_status"] = cmi.success_status
    if cmi.score_scaled is not None:
        d["cmi.score.scaled"] = str(cmi.score_scaled)
    if cmi.score_raw is not None:
        d["cmi.score.raw"] = str(cmi.score_raw)
    if cmi.score_min is not None:
        d["cmi.score.min"] = str(cmi.score_min)
    if cmi.score_max is not None:
        d["cmi.score.max"] = str(cmi.score_max)
    if cmi.total_time:
        d["cmi.total_time"] = cmi.total_time
    if cmi.suspend_data:
        d["cmi.suspend_data"] = cmi.suspend_data
    if cmi.location:
        d["cmi.location"] = cmi.location
    d["cmi.entry"] = cmi.entry or "ab-initio"
    d["cmi.mode"]   = "normal"
    d["cmi.credit"] = "credit"
    return d


def _apply_cmi_dict(cmi: ScormCmiData, data: dict) -> None:
    """Write cmi.* keys from loader back into the ScormCmiData row."""
    if "cmi.completion_status" in data:
        cmi.completion_status = data["cmi.completion_status"]
    if "cmi.success_status" in data:
        cmi.success_status = data["cmi.success_status"]
    if "cmi.score.scaled" in data:
        try:
            cmi.score_scaled = float(data["cmi.score.scaled"])
        except (ValueError, TypeError):
            pass
    if "cmi.score.raw" in data:
        try:
            cmi.score_raw = float(data["cmi.score.raw"])
        except (ValueError, TypeError):
            pass
    if "cmi.score.min" in data:
        try:
            cmi.score_min = float(data["cmi.score.min"])
        except (ValueError, TypeError):
            pass
    if "cmi.score.max" in data:
        try:
            cmi.score_max = float(data["cmi.score.max"])
        except (ValueError, TypeError):
            pass
    if "cmi.session_time" in data:
        cmi.session_time = data["cmi.session_time"]
    if "cmi.suspend_data" in data:
        cmi.suspend_data = data["cmi.suspend_data"]
    if "cmi.location" in data:
        cmi.location = data["cmi.location"]
    if "cmi.exit" in data:
        cmi.exit = data["cmi.exit"]
        # Set entry for next launch
        if data["cmi.exit"] == "suspend":
            cmi.entry = "resume"
        elif data["cmi.exit"] in ("normal", "logout", ""):
            cmi.entry = ""
    cmi.updated_at = datetime.now(timezone.utc)


# ── Endpoints ─────────────────────────────────────────────────────────────────

class InitBody(BaseModel):
    package_id: int
    sco_identifier: Optional[str] = None


@router.post("/sessions")
def initialize_session(
    body: InitBody,
    auth: tuple = Depends(_auth),
    db: Session = Depends(get_db),
):
    """
    SCORM Initialize: get or create CMI data row, return prior state for resume.
    Called synchronously by the loader via sync XHR.
    """
    user, pkg, enrollment = auth

    sco_id = body.sco_identifier or pkg.launch_href

    cmi = db.query(ScormCmiData).filter(
        ScormCmiData.user_id == user.id,
        ScormCmiData.learning_package_id == pkg.id,
        ScormCmiData.sco_identifier == sco_id,
    ).first()

    session_id = str(uuid.uuid4())

    if not cmi:
        cmi = ScormCmiData(
            user_id=user.id,
            learning_package_id=pkg.id,
            sco_identifier=sco_id,
            scorm_session_id=session_id,
            completion_status="not attempted",
            success_status="unknown",
            entry="ab-initio",
        )
        db.add(cmi)
    else:
        cmi.scorm_session_id = session_id

    db.commit()

    # Emit xAPI launched
    iri = f"http://lms.internal/courses/{enrollment.course_id}/packages/{pkg.id}"
    xapi_svc.emit(db, user, "launched", iri, pkg.title,
                  activity_type="http://adlnet.gov/expapi/activities/lesson",
                  enrollment_id=enrollment.id)
    db.commit()

    return {"session_id": session_id, "cmi_data": _cmi_to_dict(cmi)}


class CommitBody(BaseModel):
    cmi_data: dict


@router.post("/sessions/{session_id}/commit")
def commit_session(
    session_id: str,
    body: CommitBody,
    auth: tuple = Depends(_auth),
    db: Session = Depends(get_db),
):
    """Persist interim CMI state (async, fire-and-forget from loader)."""
    user, pkg, enrollment = auth

    cmi = db.query(ScormCmiData).filter(
        ScormCmiData.user_id == user.id,
        ScormCmiData.learning_package_id == pkg.id,
        ScormCmiData.scorm_session_id == session_id,
    ).first()

    if not cmi:
        # Session may have been restarted; find by package
        cmi = db.query(ScormCmiData).filter(
            ScormCmiData.user_id == user.id,
            ScormCmiData.learning_package_id == pkg.id,
        ).first()

    if cmi:
        _apply_cmi_dict(cmi, body.cmi_data)
        db.flush()

        # Find the section that owns this content item and evaluate completion
        from app.models.course import ContentItem, Section
        content_item = db.query(ContentItem).filter(
            ContentItem.id == pkg.content_item_id,
        ).first()
        if content_item:
            section = db.query(Section).filter(
                Section.id == content_item.section_id,
                Section.course_id == enrollment.course_id,
            ).first()
            if section:
                bridge.scorm_completion_to_progress(
                    db, enrollment, section, cmi, pkg, user
                )
        db.commit()

    return {"ok": True}


class TerminateBody(BaseModel):
    cmi_data: dict


@router.post("/sessions/{session_id}/terminate")
def terminate_session(
    session_id: str,
    body: TerminateBody,
    auth: tuple = Depends(_auth),
    db: Session = Depends(get_db),
):
    """Persist final CMI state, evaluate completion, bridge to section_progress."""
    user, pkg, enrollment = auth

    cmi = db.query(ScormCmiData).filter(
        ScormCmiData.user_id == user.id,
        ScormCmiData.learning_package_id == pkg.id,
        ScormCmiData.scorm_session_id == session_id,
    ).first()

    if not cmi:
        # Fallback to find by package if session_id is missing/mismatched
        cmi = db.query(ScormCmiData).filter(
            ScormCmiData.user_id == user.id,
            ScormCmiData.learning_package_id == pkg.id,
        ).first()

    if not cmi:
        raise HTTPException(status_code=404, detail="CMI session not found")

    _apply_cmi_dict(cmi, body.cmi_data)

    # SCORM 2004 default-completion rule:
    # If the SCO does not explicitly set cmi.completion_status, the LMS should
    # set the completion status to "completed" upon termination.
    if cmi.completion_status in (None, "not attempted", "unknown", ""):
        cmi.completion_status = "completed"

    cmi.scorm_session_id = None
    db.flush()

    # Find the section that owns this content item
    from app.models.course import ContentItem, Section
    content_item = db.query(ContentItem).filter(
        ContentItem.id == pkg.content_item_id,
    ).first()

    section_complete = False
    if content_item:
        section = db.query(Section).filter(
            Section.id == content_item.section_id,
            Section.course_id == enrollment.course_id,
        ).first()
        if section:
            section_complete = bridge.scorm_completion_to_progress(
                db, enrollment, section, cmi, pkg, user
            )

    # Emit xAPI terminated/completed
    iri = f"http://lms.internal/courses/{enrollment.course_id}/packages/{pkg.id}"
    xapi_svc.emit(
        db, user,
        "completed" if cmi.completion_status == "completed" else "terminated",
        iri, pkg.title,
        activity_type="http://adlnet.gov/expapi/activities/lesson",
        result={
            "completion": cmi.completion_status == "completed",
            "success": cmi.success_status == "passed",
            **({"score": {"scaled": cmi.score_scaled}} if cmi.score_scaled is not None else {}),
        },
        enrollment_id=enrollment.id,
    )
    db.commit()

    return {"ok": True, "section_complete": section_complete}
