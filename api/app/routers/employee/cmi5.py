"""
cmi5 launch, fetch token, and statement endpoints.

Three URL patterns:
  POST /my/enrollments/{id}/sections/{sid}/cmi5/launch   → create session, return launch URL
  GET  /api/cmi5/fetch/{session_id}                      → one-time token exchange (AU calls this)
  POST /api/cmi5/sessions/{session_id}/statement         → AU submits xAPI statement
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_employee, verify_csrf
from app.models.user import User
from app.models.course import Section, ContentItem, ContentType
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.package import LearningPackage, PackageFormat
from app.models.cmi5 import Cmi5Registration, Cmi5Session, Cmi5SessionState, LaunchMode
from app.config import settings
from app.services.enrollment import enrollment_deadline_passed
from app.standards import bridge, xapi as xapi_svc

router = APIRouter(tags=["employee-cmi5"])

SESSION_TTL_MINUTES = 120


# ── Employee: launch an AU ────────────────────────────────────────────────────

@router.post(
    "/my/enrollments/{enrollment_id}/sections/{section_id}/cmi5/launch",
    dependencies=[Depends(verify_csrf)],
)
def cmi5_launch(
    enrollment_id: int,
    section_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_employee),
):
    enrollment = db.query(Enrollment).filter(
        Enrollment.id == enrollment_id,
        Enrollment.user_id == user.id,
    ).first()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    if enrollment_deadline_passed(enrollment):
        enrollment.status = EnrollmentStatus.expired
        db.commit()
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
        ContentItem.type == ContentType.cmi5,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="No cmi5 content in this section")

    pkg = db.query(LearningPackage).filter(
        LearningPackage.content_item_id == item.id,
        LearningPackage.format == PackageFormat.cmi5,
    ).first()
    if not pkg:
        raise HTTPException(status_code=404, detail="cmi5 package not imported yet")

    # Get or create registration
    reg = db.query(Cmi5Registration).filter(
        Cmi5Registration.user_id == user.id,
        Cmi5Registration.learning_package_id == pkg.id,
    ).first()
    if not reg:
        reg = Cmi5Registration(
            user_id=user.id,
            learning_package_id=pkg.id,
            registration=str(uuid.uuid4()),
        )
        db.add(reg)
        db.flush()

    # Create a new session
    auth_token = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    session = Cmi5Session(
        registration_id=reg.id,
        au_index=0,
        session_id=str(uuid.uuid4()),
        auth_token=auth_token,
        launch_mode=LaunchMode.Normal,
        state=Cmi5SessionState.launched,
        expires_at=now + timedelta(minutes=SESSION_TTL_MINUTES),
    )
    db.add(session)
    db.flush()

    # Emit xAPI launched
    iri = f"http://lms.internal/courses/{enrollment.course_id}/packages/{pkg.id}"
    xapi_svc.emit(db, user, "launched", iri, pkg.title,
                  activity_type="https://w3id.org/xapi/cmi5/activitytype/learningunit",
                  enrollment_id=enrollment_id)
    db.commit()

    # Build cmi5 launch URL per spec §8.1
    # endpoint: LMS' xAPI endpoint
    # fetch: one-time token URL
    # actor: Agent JSON
    # registration: per-user-per-AU UUID
    # activityId: AU's IRI
    api_base = settings.API_EXTERNAL_URL
    endpoint = f"{api_base}/api/cmi5/xapi/"
    fetch_url = f"{api_base}/api/cmi5/fetch/{session.session_id}"
    actor = {
        "objectType": "Agent",
        "mbox": f"mailto:{user.email}",
        "name": user.name,
    }
    import json, urllib.parse
    launch_url = (
        f"{settings.CONTENT_ORIGIN}/pkg/{item.id}/{pkg.launch_href}"
        f"?endpoint={urllib.parse.quote(endpoint)}"
        f"&fetch={urllib.parse.quote(fetch_url)}"
        f"&actor={urllib.parse.quote(json.dumps(actor))}"
        f"&registration={urllib.parse.quote(reg.registration)}"
        f"&activityId={urllib.parse.quote(iri)}"
    )

    return {
        "launch_url": launch_url,
        "session_id": session.session_id,
        "registration": reg.registration,
    }


# ── fetch endpoint: one-time token exchange ───────────────────────────────────

@router.get("/api/cmi5/fetch/{session_id}")
def cmi5_fetch_token(
    session_id: str,
    db: Session = Depends(get_db),
):
    """
    AU calls this once to exchange session_id for its auth-token.
    Token is consumed: subsequent calls return 401.
    """
    session = db.query(Cmi5Session).filter(
        Cmi5Session.session_id == session_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.state != Cmi5SessionState.launched:
        raise HTTPException(status_code=401, detail="Token already consumed or session ended")

    if session.expires_at and datetime.now(timezone.utc) > session.expires_at:
        raise HTTPException(status_code=401, detail="Session expired")

    # Advance state → initialized (token consumed)
    session.state = Cmi5SessionState.initialized
    db.commit()

    # Return per cmi5 spec §8.2.1
    return {
        "auth-token": session.auth_token,
        "status": "OK",
    }


# ── xAPI statement endpoint ───────────────────────────────────────────────────

class StatementBody(BaseModel):
    statement: dict
    session_id: str


def _get_session_and_enrollment(
    session_id: str, auth_token: str, db: Session
) -> tuple[Cmi5Session, Cmi5Registration, User, Enrollment]:
    session = db.query(Cmi5Session).filter(
        Cmi5Session.session_id == session_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.auth_token != auth_token:
        raise HTTPException(status_code=401, detail="Invalid auth token")
    if session.expires_at and datetime.now(timezone.utc) > session.expires_at:
        raise HTTPException(status_code=401, detail="Session expired")

    reg = db.get(Cmi5Registration, session.registration_id)
    user = db.get(User, reg.user_id)

    enrollment = db.query(Enrollment).filter(
        Enrollment.user_id == user.id,
        Enrollment.status.in_(["enrolled", "in_progress"]),
    ).first()

    return session, reg, user, enrollment


@router.post("/api/cmi5/sessions/{session_id}/statement")
def cmi5_statement(
    session_id: str,
    body: StatementBody,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db),
):
    """
    AU submits an xAPI statement. We:
    1. Persist it via xapi_svc.emit
    2. Advance session state on terminal verbs
    3. Bridge completion/passed to section_progress
    """
    auth_token_raw = ""
    if authorization:
        auth_token_raw = authorization.replace("Basic ", "").replace("Bearer ", "").strip()

    session = db.query(Cmi5Session).filter(
        Cmi5Session.session_id == session_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if auth_token_raw and session.auth_token != auth_token_raw:
        raise HTTPException(status_code=401, detail="Invalid auth token")

    reg = db.get(Cmi5Registration, session.registration_id)
    user = db.get(User, reg.user_id)
    pkg = db.get(LearningPackage, reg.learning_package_id)

    stmt = body.statement
    verb_id = stmt.get("verb", {}).get("id", "")

    # Map cmi5 verb IRI → our key
    CMI5_VERB_MAP = {
        "https://w3id.org/xapi/adl/verbs/launched":     "launched",
        "https://w3id.org/xapi/adl/verbs/initialized":  "initialized",
        "https://w3id.org/xapi/adl/verbs/completed":    "completed",
        "https://w3id.org/xapi/adl/verbs/passed":       "passed",
        "https://w3id.org/xapi/adl/verbs/failed":       "failed",
        "https://w3id.org/xapi/adl/verbs/terminated":   "terminated",
        "https://w3id.org/xapi/adl/verbs/abandoned":    "abandoned",
    }
    verb_key = CMI5_VERB_MAP.get(verb_id, "experienced")

    # Advance session state machine
    state_transitions = {
        "initialized": Cmi5SessionState.initialized,
        "completed":   Cmi5SessionState.completed,
        "passed":      Cmi5SessionState.passed,
        "failed":      Cmi5SessionState.failed,
        "terminated":  Cmi5SessionState.terminated,
        "abandoned":   Cmi5SessionState.abandoned,
    }
    if verb_key in state_transitions:
        session.state = state_transitions[verb_key]
        db.flush()

    # Extract score from statement
    score_scaled = None
    result = stmt.get("result", {})
    score = result.get("score", {})
    if score.get("scaled") is not None:
        score_scaled = float(score["scaled"])

    # Persist statement
    iri = f"http://lms.internal/packages/{pkg.id}"
    xapi_svc.emit(
        db, user, verb_key, iri, pkg.title,
        activity_type="https://w3id.org/xapi/cmi5/activitytype/learningunit",
        result=result if result else None,
    )

    # Bridge terminal verbs to section_progress
    if verb_key in ("completed", "passed", "failed", "terminated"):
        # Find the section that has this package
        item = db.query(ContentItem).filter(
            ContentItem.id == pkg.content_item_id,
        ).first()
        if item:
            section = db.query(Section).filter(
                Section.id == item.section_id,
            ).first()
            if section and user:
                enrollment = db.query(Enrollment).filter(
                    Enrollment.user_id == user.id,
                    Enrollment.course_id == section.course_id,
                ).first()
                if enrollment and verb_key in ("completed", "passed"):
                    bridge.cmi5_moveon_to_progress(
                        db, enrollment, section, pkg, user,
                        verb_key=verb_key,
                        score_scaled=score_scaled,
                    )

    db.commit()
    return {"status": "OK", "statement_id": str(uuid.uuid4())}
