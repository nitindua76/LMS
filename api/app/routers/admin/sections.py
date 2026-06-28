from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.dependencies import require_admin, verify_csrf
from app.models.user import User
from app.models.course import Course, Section, ContentItem
from app.schemas.section import (
    SectionCreate, SectionUpdate, SectionRead, SectionReorder,
    ContentItemCreate, ContentItemUpdate, ContentItemRead,
)
from app.services.audit import audit
from app.services import storage as store

router = APIRouter(prefix="/admin/courses/{course_id}/sections", tags=["admin-sections"])


def _get_course(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


def _get_section(db: Session, course_id: int, section_id: int) -> Section:
    section = (
        db.query(Section)
        .options(joinedload(Section.content_items))
        .filter(Section.id == section_id, Section.course_id == course_id)
        .first()
    )
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    return section


@router.get("", response_model=List[SectionRead])
def list_sections(
    course_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    _get_course(db, course_id)
    return (
        db.query(Section)
        .options(joinedload(Section.content_items))
        .filter(Section.course_id == course_id)
        .order_by(Section.order_index)
        .all()
    )


@router.post("", response_model=SectionRead, status_code=201, dependencies=[Depends(verify_csrf)])
def create_section(
    course_id: int,
    body: SectionCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    _get_course(db, course_id)
    section = Section(course_id=course_id, order_index=body.order_index, title=body.title)
    db.add(section)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A section with that order_index already exists in this course",
        )
    audit(db, actor_id=actor.id, action="create_section", target_type="section",
          target_id=section.id, detail={"course_id": course_id, "title": body.title})
    db.commit()
    return _get_section(db, course_id, section.id)


@router.get("/{section_id}", response_model=SectionRead)
def get_section(
    course_id: int,
    section_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return _get_section(db, course_id, section_id)


@router.put("/{section_id}", response_model=SectionRead, dependencies=[Depends(verify_csrf)])
def update_section(
    course_id: int,
    section_id: int,
    body: SectionUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    section = _get_section(db, course_id, section_id)
    if body.order_index is not None:
        section.order_index = body.order_index
    if body.title is not None:
        section.title = body.title
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="order_index collision in this course")
    audit(db, actor_id=actor.id, action="update_section", target_type="section", target_id=section_id)
    db.commit()
    return _get_section(db, course_id, section_id)


@router.delete("/{section_id}", status_code=204, dependencies=[Depends(verify_csrf)])
def delete_section(
    course_id: int,
    section_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    section = _get_section(db, course_id, section_id)
    try:
        db.delete(section)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Cannot delete: section has dependent progress, quiz, or content records",
        )
    audit(db, actor_id=actor.id, action="delete_section", target_type="section",
          target_id=section_id, detail={"course_id": course_id})
    db.commit()


@router.post("/reorder", dependencies=[Depends(verify_csrf)])
def reorder_sections(
    course_id: int,
    body: SectionReorder,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    """Re-assign order_index to sections based on the provided ordered list of IDs."""
    _get_course(db, course_id)
    sections = {
        s.id: s
        for s in db.query(Section).filter(Section.course_id == course_id).all()
    }
    if set(body.section_ids) != set(sections.keys()):
        raise HTTPException(status_code=422, detail="section_ids must match all sections in this course")

    # Temporarily set large indices to avoid unique constraint collisions
    for i, sid in enumerate(body.section_ids):
        sections[sid].order_index = 10000 + i
    db.flush()
    for i, sid in enumerate(body.section_ids):
        sections[sid].order_index = i + 1
    db.flush()

    audit(db, actor_id=actor.id, action="reorder_sections", target_type="course",
          target_id=course_id, detail={"order": body.section_ids})
    db.commit()
    return {"message": "Sections reordered"}


# ── Content items (nested under sections) ─────────────────────────────────────

content_router = APIRouter(
    prefix="/admin/courses/{course_id}/sections/{section_id}/content",
    tags=["admin-content"],
)


@content_router.get("", response_model=List[ContentItemRead])
def list_content(
    course_id: int,
    section_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    _get_section(db, course_id, section_id)
    return (
        db.query(ContentItem)
        .filter(ContentItem.section_id == section_id)
        .order_by(ContentItem.order_index)
        .all()
    )


@content_router.post("", response_model=ContentItemRead, status_code=201,
                     dependencies=[Depends(verify_csrf)])
def create_content(
    course_id: int,
    section_id: int,
    body: ContentItemCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    _get_section(db, course_id, section_id)
    item = ContentItem(
        section_id=section_id,
        order_index=body.order_index,
        type=body.type,
        url=body.url,
        video_duration_sec=body.video_duration_sec,
    )
    db.add(item)
    db.flush()
    audit(db, actor_id=actor.id, action="create_content_item", target_type="content_item",
          target_id=item.id, detail={"section_id": section_id, "type": body.type.value})
    db.commit()
    db.refresh(item)
    return item


@content_router.put("/{item_id}", response_model=ContentItemRead,
                    dependencies=[Depends(verify_csrf)])
def update_content(
    course_id: int,
    section_id: int,
    item_id: int,
    body: ContentItemUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    _get_section(db, course_id, section_id)
    item = db.query(ContentItem).filter(
        ContentItem.id == item_id, ContentItem.section_id == section_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Content item not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(item, field, value)
    db.flush()
    audit(db, actor_id=actor.id, action="update_content_item", target_type="content_item",
          target_id=item_id)
    db.commit()
    db.refresh(item)
    return item


@content_router.delete("/{item_id}", status_code=204, dependencies=[Depends(verify_csrf)])
def delete_content(
    course_id: int,
    section_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    _get_section(db, course_id, section_id)
    item = db.query(ContentItem).filter(
        ContentItem.id == item_id, ContentItem.section_id == section_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Content item not found")
    db.delete(item)
    audit(db, actor_id=actor.id, action="delete_content_item", target_type="content_item",
          target_id=item_id)
    db.commit()


@content_router.post(
    "/{item_id}/upload",
    response_model=ContentItemRead,
    dependencies=[Depends(verify_csrf)],
)
def upload_content_file(
    course_id: int,
    section_id: int,
    item_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    """
    Upload a video or PDF file to object storage and record the storage_key on the
    content item. After this call, the employee-facing GET will serve a short-lived
    signed URL — the raw storage key is never exposed to the client.
    """
    _get_section(db, course_id, section_id)
    item = db.query(ContentItem).filter(
        ContentItem.id == item_id, ContentItem.section_id == section_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Content item not found")

    filename = file.filename or f"item_{item_id}"
    storage_key = f"content/{item_id}/{filename}"
    content_type = store.content_type_for(filename)

    try:
        store.ensure_bucket()
        store.upload_fileobj(storage_key, file.file, content_type)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Storage upload failed: {exc}")

    item.storage_key = storage_key
    db.flush()
    audit(
        db, actor_id=actor.id, action="upload_content_file",
        target_type="content_item", target_id=item_id,
        detail={"storage_key": storage_key, "content_type": content_type},
    )
    db.commit()
    db.refresh(item)
    return item
