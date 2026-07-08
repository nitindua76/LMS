import csv
import io
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.dependencies import require_admin, verify_csrf
from app.models.user import User, UserRole
from app.models.discipline import Discipline
from app.models.level import Level
from app.schemas.common import PaginatedResponse
from app.schemas.user import UserCreate, UserUpdate, UserRead, UserSummary, UserResetPassword, CSVRowResult
from app.schemas.controller import SetControllerRequest
from app.services import auth as auth_svc
from app.services.audit import audit
from app.services.controller import assign_controller, ControllerAssignmentError
from app.models.controller_history import ControllerAssignmentSource
from app.services.redis_client import get_redis

router = APIRouter(prefix="/admin/users", tags=["admin-users"])


def _load_user(db: Session, user_id: int) -> User:
    user = (
        db.query(User)
        .options(joinedload(User.discipline), joinedload(User.level))
        .filter(User.id == user_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("", response_model=PaginatedResponse[UserSummary])
def list_users(
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = Query(None),
    discipline_id: Optional[int] = Query(None),
    level_id: Optional[int] = Query(None),
    active: Optional[bool] = Query(None),
    role: Optional[UserRole] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    q = db.query(User)
    if search:
        like = f"%{search}%"
        q = q.filter((User.name.ilike(like)) | (User.email.ilike(like)))
    if discipline_id is not None:
        q = q.filter(User.discipline_id == discipline_id)
    if level_id is not None:
        q = q.filter(User.level_id == level_id)
    if active is not None:
        q = q.filter(User.active == active)
    if role is not None:
        q = q.filter(User.role == role)

    total = q.count()
    items = q.order_by(User.name).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(verify_csrf)])
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    email = body.email.lower().strip()
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    if body.discipline_id and not db.get(Discipline, body.discipline_id):
        raise HTTPException(status_code=422, detail="Discipline not found")
    if body.level_id and not db.get(Level, body.level_id):
        raise HTTPException(status_code=422, detail="Level not found")

    user = User(
        name=body.name.strip(),
        email=email,
        password_hash=auth_svc.hash_password(body.password),
        role=body.role,
        discipline_id=body.discipline_id,
        level_id=body.level_id,
        force_password_change=True,
    )
    db.add(user)
    db.flush()
    audit(db, actor_id=actor.id, action="create_user", target_type="user",
          target_id=user.id, detail={"email": email, "role": body.role.value})
    db.commit()
    return _load_user(db, user.id)


@router.get("/{user_id}", response_model=UserRead)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return _load_user(db, user_id)


@router.put("/{user_id}", response_model=UserRead, dependencies=[Depends(verify_csrf)])
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    user = _load_user(db, user_id)
    if body.name is not None:
        user.name = body.name.strip()
    if body.email is not None:
        user.email = body.email.lower().strip()
    if body.role is not None:
        user.role = body.role
    if body.discipline_id is not None:
        if not db.get(Discipline, body.discipline_id):
            raise HTTPException(status_code=422, detail="Discipline not found")
        user.discipline_id = body.discipline_id
    if body.level_id is not None:
        if not db.get(Level, body.level_id):
            raise HTTPException(status_code=422, detail="Level not found")
        user.level_id = body.level_id
    if body.active is not None and body.active != user.active:
        user.active = body.active
        if not body.active:
            auth_svc.revoke_all_user_refresh_tokens(user.id, get_redis())
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email already in use")
    audit(db, actor_id=actor.id, action="update_user", target_type="user",
          target_id=user.id)
    db.commit()
    return _load_user(db, user.id)


@router.post("/{user_id}/deactivate", dependencies=[Depends(verify_csrf)])
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.active:
        return {"message": "Already deactivated"}
    user.active = False
    auth_svc.revoke_all_user_refresh_tokens(user.id, get_redis())
    audit(db, actor_id=actor.id, action="deactivate_user", target_type="user", target_id=user_id)
    db.commit()
    return {"message": "User deactivated"}


@router.post("/{user_id}/activate", dependencies=[Depends(verify_csrf)])
def activate_user(
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.active = True
    audit(db, actor_id=actor.id, action="activate_user", target_type="user", target_id=user_id)
    db.commit()
    return {"message": "User activated"}


@router.post("/{user_id}/reset-password", dependencies=[Depends(verify_csrf)])
def reset_password(
    user_id: int,
    body: UserResetPassword,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = auth_svc.hash_password(body.new_password)
    user.force_password_change = True
    # Revoke existing sessions so they must log in again with new password
    auth_svc.revoke_all_user_refresh_tokens(user.id, get_redis())
    audit(db, actor_id=actor.id, action="reset_password", target_type="user", target_id=user_id)
    db.commit()
    return {"message": "Password reset. User will be prompted to change it on next login."}


@router.put("/{user_id}/controller", response_model=UserRead, dependencies=[Depends(verify_csrf)])
def set_controller(
    user_id: int,
    body: SetControllerRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    """
    Manually assign (or clear) a user's controlling officer. This is the interim
    path until the company HR API sync is wired up, and remains the correction
    path afterwards.
    """
    user = _load_user(db, user_id)
    new_controller = None
    if body.controller_id is not None:
        new_controller = db.get(User, body.controller_id)
        if not new_controller:
            raise HTTPException(status_code=422, detail="Controller not found")

    try:
        assign_controller(
            db, user=user, new_controller=new_controller,
            source=ControllerAssignmentSource.manual, actor_id=actor.id,
        )
    except ControllerAssignmentError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db.commit()
    return _load_user(db, user.id)


@router.post("/import/csv", response_model=List[CSVRowResult], dependencies=[Depends(verify_csrf)])
async def import_users_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    content = await file.read()
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    required_fields = {"name", "email", "discipline", "level"}
    if not reader.fieldnames or not required_fields.issubset(set(f.strip() for f in reader.fieldnames)):
        raise HTTPException(
            status_code=422,
            detail=f"CSV must have columns: {', '.join(required_fields)}",
        )

    # Cache lookups
    disciplines = {d.name.lower(): d for d in db.query(Discipline).all()}
    levels = {lv.code.upper(): lv for lv in db.query(Level).all()}

    results: List[CSVRowResult] = []
    for idx, row in enumerate(reader, start=2):
        email = (row.get("email") or "").strip().lower()
        name = (row.get("name") or "").strip()
        disc_name = (row.get("discipline") or "").strip()
        level_code = (row.get("level") or "").strip().upper()
        role_str = (row.get("role") or "employee").strip().lower()

        if not email or not name:
            results.append(CSVRowResult(row=idx, email=email, status="error", error="name and email are required"))
            continue

        if role_str not in ("admin", "employee"):
            role_str = "employee"

        disc = disciplines.get(disc_name.lower())
        if not disc:
            results.append(CSVRowResult(row=idx, email=email, status="error",
                                        error=f"Unknown discipline: {disc_name}"))
            continue

        lvl = levels.get(level_code)
        if not lvl:
            results.append(CSVRowResult(row=idx, email=email, status="error",
                                        error=f"Unknown level: {level_code}"))
            continue

        existing = db.query(User).filter(User.email == email).first()
        if existing:
            results.append(CSVRowResult(row=idx, email=email, status="error",
                                        error="Email already registered"))
            continue

        user = User(
            name=name,
            email=email,
            password_hash=auth_svc.hash_password("ChangeMe123!"),
            role=UserRole(role_str),
            discipline_id=disc.id,
            level_id=lvl.id,
            force_password_change=True,
        )
        db.add(user)
        try:
            db.flush()
            audit(db, actor_id=actor.id, action="csv_import_user", target_type="user",
                  target_id=user.id, detail={"email": email})
            results.append(CSVRowResult(row=idx, email=email, status="imported"))
        except IntegrityError:
            db.rollback()
            results.append(CSVRowResult(row=idx, email=email, status="error",
                                        error="Duplicate email (concurrent conflict)"))

    db.commit()
    return results
