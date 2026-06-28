"""
The single authoritative bridge between external standards state
(SCORM cmi.* / cmi5 verbs) and internal section_progress.

Invariants enforced here:
- Source-agnostic: completion criteria checked regardless of source.
- Section N is open only when sections 1..N-1 all have completed_at set.
- Course completion fires when all sections are done.
- xAPI emit for every terminal event.
"""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session

from app.models.enrollment import (
    SectionProgress, Enrollment, EnrollmentStatus, ProgressSource,
)
from app.models.course import Section
from app.models.package import LearningPackage, ScormCmiData, MoveOn
from app.models.user import User
from app.standards import xapi as xapi_svc


# ── Section lock gate ────────────────────────────────────────────────────────

def is_section_unlocked(
    db: Session,
    enrollment: Enrollment,
    section: Section,
) -> bool:
    """Section N is open iff all sections with order_index < N are complete."""
    if section.order_index == 0:
        return True

    from app.models.course import Section as S
    prior = db.query(S).filter(
        S.course_id == section.course_id,
        S.order_index < section.order_index,
    ).all()

    if not prior:
        return True

    prog_map = {
        sp.section_id: sp
        for sp in db.query(SectionProgress).filter(
            SectionProgress.enrollment_id == enrollment.id,
            SectionProgress.section_id.in_([s.id for s in prior]),
        ).all()
    }

    return all(
        prog_map.get(s.id) and prog_map[s.id].completed_at
        for s in prior
    )


# ── Native content → progress ────────────────────────────────────────────────

def native_content_to_progress(
    db: Session,
    enrollment: Enrollment,
    section: Section,
    user: User,
    content_done: bool = True,
    quiz_passed: Optional[bool] = None,
) -> bool:
    """Mark native content/quiz progress. Returns True when section fully complete."""
    sp = _get_or_create_sp(db, enrollment, section, ProgressSource.native)

    if content_done:
        sp.content_done = True
    if quiz_passed is not None:
        sp.quiz_passed = quiz_passed

    has_quiz = section.quiz is not None
    fully_done = sp.content_done and (not has_quiz or sp.quiz_passed)

    if fully_done and not sp.completed_at:
        sp.completed_at = datetime.now(timezone.utc)
        db.flush()
        iri = f"http://lms.internal/courses/{enrollment.course_id}/sections/{section.id}"
        xapi_svc.emit(
            db, user, "completed", iri, section.title,
            activity_type="http://adlnet.gov/expapi/activities/lesson",
            enrollment_id=enrollment.id,
        )
        _check_course_completion(db, enrollment, user)
        return True

    db.flush()
    return False


# ── SCORM → progress ─────────────────────────────────────────────────────────

def get_sco_identifiers_from_manifest(manifest_xml: bytes) -> list[str]:
    import xml.etree.ElementTree as ET
    root = ET.fromstring(manifest_xml)

    # 1. Map resource ID -> href and scormType
    resources = {}
    for el in root.iter():
        if el.tag.endswith("resource"):
            res_id = el.attrib.get("identifier")
            href = el.attrib.get("href")
            scorm_type = ""
            for k, v in el.attrib.items():
                if k.split("}")[-1] == "scormType":
                    scorm_type = v.lower()
                    break
            res_type = el.attrib.get("type", "").lower()
            resources[res_id] = {
                "href": href,
                "is_sco": (scorm_type == "sco" or "sco" in res_type)
            }

    # 2. Walk items in the organization and collect referenced SCOs with parameters
    sco_identifiers = []
    for el in root.iter():
        if el.tag.endswith("item"):
            res_ref = el.attrib.get("identifierref")
            if res_ref in resources and resources[res_ref]["is_sco"]:
                href = resources[res_ref]["href"]
                if href:
                    params = el.attrib.get("parameters", "")
                    sco_identifiers.append(href + params)

    # Fallback to resources if no items are found
    if not sco_identifiers:
        for res_id, res_info in resources.items():
            if res_info["is_sco"] and res_info["href"]:
                sco_identifiers.append(res_info["href"])

    return sco_identifiers


def scorm_completion_to_progress(
    db: Session,
    enrollment: Enrollment,
    section: Section,
    cmi_data: ScormCmiData,
    package: LearningPackage,
    user: User,
) -> bool:
    """Called after SCO Terminate. Returns True if section just completed."""
    if cmi_data.completion_status != "completed":
        return False

    if cmi_data.success_status == "failed":
        return False

    if package.mastery_score is not None:
        if (cmi_data.score_scaled or 0.0) < package.mastery_score:
            return False

    # Retrieve all SCOs in the package from manifest to support multi-SCO
    try:
        from app.services import storage as store
        manifest_bytes = store.download_bytes(f"pkg/{package.content_item_id}/imsmanifest.xml")
        sco_identifiers = get_sco_identifiers_from_manifest(manifest_bytes)
    except Exception:
        # Fallback to single SCO if manifest cannot be read
        sco_identifiers = [cmi_data.sco_identifier]

    # Find all completed SCOs for this user and package where success_status is not "failed"
    completed_scos = db.query(ScormCmiData.sco_identifier).filter(
        ScormCmiData.user_id == user.id,
        ScormCmiData.learning_package_id == package.id,
        ScormCmiData.completion_status == "completed",
        ScormCmiData.success_status != "failed",
    ).all()
    completed_set = {row[0] for row in completed_scos}

    # Ensure current one is counted as completed
    completed_set.add(cmi_data.sco_identifier)

    # Normalize paths to be immune to Windows backslash/forward slash, casing, and query parameter discrepancies
    def normalize_path(p: str) -> str:
        if not p:
            return ""
        p = p.replace("\\", "/").strip("/")
        if "?" in p:
            p = p.split("?")[0]
        return p.lower()

    norm_manifest = {normalize_path(s) for s in sco_identifiers if s}
    norm_completed = {normalize_path(s) for s in completed_set if s}

    is_single_sco = len(norm_manifest) <= 1

    if not is_single_sco and not norm_manifest.issubset(norm_completed):
        return False

    sp = _get_or_create_sp(db, enrollment, section, ProgressSource.scorm)
    if sp.completed_at:
        return False  # already done

    sp.content_done = True
    sp.quiz_passed = True
    sp.completed_at = datetime.now(timezone.utc)
    db.flush()

    iri = f"http://lms.internal/courses/{enrollment.course_id}/sections/{section.id}/scorm"
    score_result = {"scaled": cmi_data.score_scaled} if cmi_data.score_scaled is not None else None
    xapi_svc.emit(
        db, user, "completed", iri, section.title,
        activity_type="http://adlnet.gov/expapi/activities/lesson",
        result={
            "completion": True,
            "success": cmi_data.success_status == "passed",
            **({"score": score_result} if score_result else {}),
        },
        enrollment_id=enrollment.id,
    )
    _check_course_completion(db, enrollment, user)
    return True


# ── cmi5 → progress ──────────────────────────────────────────────────────────

def cmi5_moveon_to_progress(
    db: Session,
    enrollment: Enrollment,
    section: Section,
    package: LearningPackage,
    user: User,
    verb_key: str,
    score_scaled: Optional[float] = None,
) -> bool:
    """Called when AU emits a terminal verb. Returns True if moveOn satisfied."""
    move_on = package.move_on or MoveOn.completed_or_passed

    satisfied = {
        MoveOn.not_applicable:       True,
        MoveOn.passed:               verb_key == "passed",
        MoveOn.completed:            verb_key == "completed",
        MoveOn.completed_and_passed: verb_key in ("completed", "passed"),
        MoveOn.completed_or_passed:  verb_key in ("completed", "passed"),
    }.get(move_on, False)

    if not satisfied:
        return False

    sp = _get_or_create_sp(db, enrollment, section, ProgressSource.cmi5)
    if sp.completed_at:
        return False

    sp.content_done = True
    sp.quiz_passed = True
    sp.completed_at = datetime.now(timezone.utc)
    db.flush()

    iri = f"http://lms.internal/courses/{enrollment.course_id}/sections/{section.id}/cmi5"
    emit_verb = verb_key if verb_key in ("completed", "passed") else "completed"
    xapi_svc.emit(
        db, user, emit_verb, iri, section.title,
        activity_type="http://adlnet.gov/expapi/activities/lesson",
        result={
            "completion": True,
            "success": verb_key == "passed",
            **({"score": {"scaled": score_scaled}} if score_scaled is not None else {}),
        },
        enrollment_id=enrollment.id,
    )
    _check_course_completion(db, enrollment, user)
    return True


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_or_create_sp(
    db: Session,
    enrollment: Enrollment,
    section: Section,
    source: ProgressSource,
) -> SectionProgress:
    sp = db.query(SectionProgress).filter(
        SectionProgress.enrollment_id == enrollment.id,
        SectionProgress.section_id == section.id,
    ).first()
    if not sp:
        sp = SectionProgress(
            enrollment_id=enrollment.id,
            section_id=section.id,
            source=source,
        )
        db.add(sp)
        db.flush()
    return sp


def _check_course_completion(
    db: Session,
    enrollment: Enrollment,
    user: User,
) -> None:
    """If all sections complete, mark enrollment completed and emit xAPI."""
    from app.models.course import Section as S
    sections = db.query(S).filter(S.course_id == enrollment.course_id).all()
    if not sections:
        return

    prog_map = {
        sp.section_id: sp
        for sp in db.query(SectionProgress).filter(
            SectionProgress.enrollment_id == enrollment.id,
        ).all()
    }

    all_done = all(
        prog_map.get(s.id) and prog_map[s.id].completed_at
        for s in sections
    )

    if all_done and enrollment.status != EnrollmentStatus.completed:
        enrollment.status = EnrollmentStatus.completed
        db.flush()
        iri = f"http://lms.internal/courses/{enrollment.course_id}"
        course = enrollment.course
        xapi_svc.emit(
            db, user, "completed", iri, course.title,
            result={"completion": True, "success": True},
            enrollment_id=enrollment.id,
        )
