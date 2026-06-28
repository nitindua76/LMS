from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.dependencies import require_admin, verify_csrf
from app.models.user import User
from app.models.discipline import Discipline
from app.schemas.discipline import DisciplineCreate, DisciplineUpdate, DisciplineRead
from app.schemas.common import PaginatedResponse
from app.services.audit import audit

router = APIRouter(prefix="/admin/disciplines", tags=["admin-disciplines"])


@router.get("", response_model=PaginatedResponse[DisciplineRead])
def list_disciplines(
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    offset = (page - 1) * page_size
    total = db.query(Discipline).count()
    items = db.query(Discipline).order_by(Discipline.name).offset(offset).limit(page_size).all()
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=DisciplineRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(verify_csrf)])
def create_discipline(
    body: DisciplineCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    obj = Discipline(name=body.name)
    db.add(obj)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Discipline name already exists")
    audit(db, actor_id=actor.id, action="create_discipline", target_type="discipline",
          target_id=obj.id, detail={"name": obj.name})
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{discipline_id}", response_model=DisciplineRead)
def get_discipline(
    discipline_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    obj = db.get(Discipline, discipline_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Discipline not found")
    return obj


@router.put("/{discipline_id}", response_model=DisciplineRead, dependencies=[Depends(verify_csrf)])
def update_discipline(
    discipline_id: int,
    body: DisciplineUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    obj = db.get(Discipline, discipline_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Discipline not found")
    obj.name = body.name
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Discipline name already exists")
    audit(db, actor_id=actor.id, action="update_discipline", target_type="discipline",
          target_id=obj.id, detail={"name": obj.name})
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{discipline_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[Depends(verify_csrf)])
def delete_discipline(
    discipline_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    obj = db.get(Discipline, discipline_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Discipline not found")
    try:
        db.delete(obj)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Cannot delete: discipline is referenced by users or course targets",
        )
    audit(db, actor_id=actor.id, action="delete_discipline", target_type="discipline",
          target_id=discipline_id)
    db.commit()
