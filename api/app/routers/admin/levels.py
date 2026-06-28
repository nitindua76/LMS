from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.dependencies import require_admin, verify_csrf
from app.models.user import User
from app.models.level import Level
from app.schemas.level import LevelCreate, LevelUpdate, LevelRead
from app.schemas.common import PaginatedResponse
from app.services.audit import audit

router = APIRouter(prefix="/admin/levels", tags=["admin-levels"])


@router.get("", response_model=PaginatedResponse[LevelRead])
def list_levels(
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    offset = (page - 1) * page_size
    total = db.query(Level).count()
    items = db.query(Level).order_by(Level.rank).offset(offset).limit(page_size).all()
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=LevelRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(verify_csrf)])
def create_level(
    body: LevelCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    obj = Level(code=body.code.upper(), name=body.name, rank=body.rank)
    db.add(obj)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Level code already exists")
    audit(db, actor_id=actor.id, action="create_level", target_type="level",
          target_id=obj.id, detail={"code": obj.code})
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{level_id}", response_model=LevelRead)
def get_level(
    level_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    obj = db.get(Level, level_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Level not found")
    return obj


@router.put("/{level_id}", response_model=LevelRead, dependencies=[Depends(verify_csrf)])
def update_level(
    level_id: int,
    body: LevelUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    obj = db.get(Level, level_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Level not found")
    if body.code is not None:
        obj.code = body.code.upper()
    if body.name is not None:
        obj.name = body.name
    if body.rank is not None:
        obj.rank = body.rank
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Level code already exists")
    audit(db, actor_id=actor.id, action="update_level", target_type="level",
          target_id=obj.id, detail={"code": obj.code})
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{level_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(verify_csrf)])
def delete_level(
    level_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    obj = db.get(Level, level_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Level not found")
    try:
        db.delete(obj)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Cannot delete: level is referenced by users or course targets",
        )
    audit(db, actor_id=actor.id, action="delete_level", target_type="level",
          target_id=level_id)
    db.commit()
