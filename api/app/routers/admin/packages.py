"""Admin: SCORM 2004 / cmi5 package import and management."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin, verify_csrf
from app.models.user import User
from app.models.course import ContentItem, ContentType
from app.models.package import LearningPackage, PackageFormat, SequencingMode, MoveOn
from app.models.audit import AuditLog
from app.config import settings
from app.services import storage as store

router = APIRouter(prefix="/admin", tags=["admin-packages"])


def _detect_format(zip_bytes: bytes) -> str:
    import zipfile, io
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = [n.lower() for n in zf.namelist()]
        if "cmi5.xml" in names:
            return "cmi5"
        if "imsmanifest.xml" in names:
            return "scorm_2004"
    raise ValueError("Unrecognised package: must contain imsmanifest.xml (SCORM 2004) or cmi5.xml (cmi5)")


@router.post("/content-items/{item_id}/package", dependencies=[Depends(verify_csrf)])
def import_package(
    item_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Upload a SCORM 2004 or cmi5 .zip and register it against a content item.
    Rejects: SCORM 1.2, full-SN packages, anything not a recognised PIF.
    """
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=422, detail="File must be a .zip archive")

    item = db.get(ContentItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Content item not found")

    zip_bytes = file.file.read()

    # Detect format
    try:
        fmt_str = _detect_format(zip_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Ensure MinIO bucket exists
    try:
        store.ensure_bucket()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Storage unavailable: {e}")

    storage_root = f"pkg/{item_id}"

    if fmt_str == "scorm_2004":
        from app.services.scorm.parser import parse_scorm_zip, extract_scorm_zip
        try:
            meta = parse_scorm_zip(zip_bytes)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

        extract_scorm_zip(zip_bytes, storage_root, store.upload_bytes)

        pkg = LearningPackage(
            content_item_id=item_id,
            format=PackageFormat.scorm_2004,
            edition=meta.edition,
            identifier=meta.identifier,
            title=meta.title,
            version=meta.version,
            launch_href=meta.launch_href,
            storage_root=storage_root,
            sequencing_mode=SequencingMode(meta.sequencing_mode),
            mastery_score=meta.mastery_score,
            move_on=None,
        )
        item.type = ContentType.scorm

    else:  # cmi5
        from app.services.cmi5.parser import parse_cmi5_zip, extract_cmi5_zip
        try:
            meta = parse_cmi5_zip(zip_bytes)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

        extract_cmi5_zip(zip_bytes, storage_root, store.upload_bytes)

        # Use first AU's launch_href and moveOn
        first_au = meta.aus[0] if meta.aus else None
        launch_href = first_au.launch_href if first_au else ""
        move_on_str = first_au.move_on if first_au else "CompletedOrPassed"
        mastery_score = first_au.mastery_score if first_au else None

        # Map cmi5 moveOn string → MoveOn enum
        _moveon_map = {
            "Passed":              MoveOn.passed,
            "Completed":           MoveOn.completed,
            "CompletedAndPassed":  MoveOn.completed_and_passed,
            "CompletedOrPassed":   MoveOn.completed_or_passed,
            "NotApplicable":       MoveOn.not_applicable,
        }
        move_on = _moveon_map.get(move_on_str, MoveOn.completed_or_passed)

        pkg = LearningPackage(
            content_item_id=item_id,
            format=PackageFormat.cmi5,
            identifier=meta.identifier,
            title=meta.title,
            launch_href=launch_href,
            storage_root=storage_root,
            sequencing_mode=SequencingMode.single_sco,
            mastery_score=mastery_score,
            move_on=move_on,
        )
        item.type = ContentType.cmi5

    db.add(pkg)
    db.add(AuditLog(
        actor_id=admin.id,
        action="package.import",
        target_type="content_item",
        target_id=str(item_id),
        detail={"format": fmt_str, "title": pkg.title},
    ))
    db.commit()
    db.refresh(pkg)

    return {
        "id": pkg.id,
        "format": pkg.format.value,
        "title": pkg.title,
        "edition": pkg.edition,
        "identifier": pkg.identifier,
        "launch_href": pkg.launch_href,
        "sequencing_mode": pkg.sequencing_mode.value,
        "mastery_score": pkg.mastery_score,
        "move_on": pkg.move_on.value if pkg.move_on else None,
        "storage_root": pkg.storage_root,
    }


@router.get("/packages/{pkg_id}")
def get_package(
    pkg_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    pkg = db.get(LearningPackage, pkg_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    return {
        "id": pkg.id,
        "content_item_id": pkg.content_item_id,
        "format": pkg.format.value,
        "title": pkg.title,
        "edition": pkg.edition,
        "identifier": pkg.identifier,
        "version": pkg.version,
        "launch_href": pkg.launch_href,
        "storage_root": pkg.storage_root,
        "sequencing_mode": pkg.sequencing_mode.value,
        "mastery_score": pkg.mastery_score,
        "move_on": pkg.move_on.value if pkg.move_on else None,
        "created_at": pkg.created_at.isoformat(),
    }


@router.get("/packages/{pkg_id}/launch-url")
def package_launch_url(
    pkg_id: int,
    enrollment_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin preview: generate a SCORM launch URL."""
    from app.services.scorm.token import create_scorm_token
    pkg = db.get(LearningPackage, pkg_id)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")

    token = create_scorm_token(admin.id, pkg_id, enrollment_id)
    # pkg= LearningPackage.id (encoded in token for runtime auth)
    # ci=  ContentItem.id (used by loader to build the asset path;
    #       matches the storage key prefix pkg/{content_item_id}/…)
    loader_url = (
        f"{settings.CONTENT_ORIGIN}/loader"
        f"?pkg={pkg_id}&ci={pkg.content_item_id}&sco={pkg.launch_href}&token={token}"
        f"&api={settings.API_EXTERNAL_URL}"
    )
    return {"launch_url": loader_url, "token": token}
