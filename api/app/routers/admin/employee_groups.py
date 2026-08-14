"""
Admin CRUD for dynamic EmployeeGroups, plus the live-preview endpoint the
group builder UI calls while an admin is still editing rules (before
anything is saved), and the course<->group targeting endpoints (mirrors
admin/courses.py's target-user endpoints, just for a whole group instead of
one user at a time).
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import require_admin, verify_csrf
from app.models.course import Course
from app.models.employee_group import EmployeeGroup, EmployeeGroupRule, CourseTargetGroup
from app.models.user import User
from app.schemas.employee_group import (
    EmployeeGroupCreate, EmployeeGroupUpdate, EmployeeGroupRead, EmployeeGroupSummary,
    PreviewRequest, PreviewResponse, PreviewMember,
    GroupMember, GroupMembersResponse,
    CourseTargetGroupRead, CourseTargetGroupCreate,
)
from app.services.audit import audit
from app.services.employee_groups import (
    count_group_members, preview_group_members, list_group_members, InvalidRuleError,
)

router = APIRouter(prefix="/admin/employee-groups", tags=["admin-employee-groups"])


def _load_group(db: Session, group_id: int) -> EmployeeGroup:
    group = (
        db.query(EmployeeGroup)
        .options(joinedload(EmployeeGroup.rules))
        .filter(EmployeeGroup.id == group_id)
        .first()
    )
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


def _to_read(db: Session, group: EmployeeGroup) -> EmployeeGroupRead:
    try:
        count = count_group_members(db, group)
    except InvalidRuleError:
        count = 0
    return EmployeeGroupRead(
        id=group.id, name=group.name, description=group.description, match_type=group.match_type,
        created_at=group.created_at, updated_at=group.updated_at,
        rules=list(group.rules), member_count=count,
    )


@router.get("", response_model=List[EmployeeGroupSummary])
def list_groups(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    groups = db.query(EmployeeGroup).options(joinedload(EmployeeGroup.rules)).order_by(EmployeeGroup.name).all()
    out = []
    for g in groups:
        try:
            count = count_group_members(db, g)
        except InvalidRuleError:
            count = 0
        out.append(EmployeeGroupSummary(
            id=g.id, name=g.name, description=g.description, match_type=g.match_type,
            member_count=count, rule_count=len(g.rules),
        ))
    return out


@router.post("", response_model=EmployeeGroupRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(verify_csrf)])
def create_group(
    body: EmployeeGroupCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    group = EmployeeGroup(
        name=body.name.strip(), description=body.description, match_type=body.match_type,
        created_by_id=actor.id,
    )
    db.add(group)
    db.flush()
    for r in body.rules:
        db.add(EmployeeGroupRule(group_id=group.id, field=r.field, operator=r.operator, value=r.value))
    db.flush()
    audit(db, actor_id=actor.id, action="create_employee_group", target_type="employee_group",
          target_id=group.id, detail={"name": group.name, "rule_count": len(body.rules)})
    db.commit()
    return _to_read(db, _load_group(db, group.id))


@router.get("/{group_id}", response_model=EmployeeGroupRead)
def get_group(
    group_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return _to_read(db, _load_group(db, group_id))


@router.put("/{group_id}", response_model=EmployeeGroupRead, dependencies=[Depends(verify_csrf)])
def update_group(
    group_id: int,
    body: EmployeeGroupUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    group = _load_group(db, group_id)
    if body.name is not None:
        group.name = body.name.strip()
    if body.description is not None:
        group.description = body.description
    if body.match_type is not None:
        group.match_type = body.match_type
    db.flush()
    audit(db, actor_id=actor.id, action="update_employee_group", target_type="employee_group", target_id=group.id)
    db.commit()
    return _to_read(db, _load_group(db, group.id))


@router.delete("/{group_id}", status_code=204, dependencies=[Depends(verify_csrf)])
def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    group = _load_group(db, group_id)
    db.delete(group)
    audit(db, actor_id=actor.id, action="delete_employee_group", target_type="employee_group", target_id=group_id)
    db.commit()


# ── Rules ────────────────────────────────────────────────────────────────────

@router.put("/{group_id}/rules", response_model=EmployeeGroupRead, dependencies=[Depends(verify_csrf)])
def replace_rules(
    group_id: int,
    body: PreviewRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    """
    Wholesale replace — the builder UI edits a group's whole rule set at
    once (add/remove/reorder), so there's no meaningful per-rule PATCH here;
    simplest correct semantics is "this is now the complete rule list."
    """
    group = _load_group(db, group_id)
    group.match_type = body.match_type
    for r in list(group.rules):
        db.delete(r)
    db.flush()
    for r in body.rules:
        db.add(EmployeeGroupRule(group_id=group.id, field=r.field, operator=r.operator, value=r.value))
    db.flush()
    audit(db, actor_id=actor.id, action="update_employee_group_rules", target_type="employee_group",
          target_id=group.id, detail={"rule_count": len(body.rules), "match_type": body.match_type.value})
    db.commit()
    return _to_read(db, _load_group(db, group.id))


@router.post("/preview", response_model=PreviewResponse)
def preview(
    body: PreviewRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Live 'N employees currently match' feedback for the builder UI, before
    anything is saved — evaluates the candidate rule set against real data
    without touching the database.
    """
    try:
        total, sample = preview_group_members(
            db, [r.model_dump() for r in body.rules], match_type=body.match_type,
        )
    except InvalidRuleError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return PreviewResponse(
        total=total,
        sample=[PreviewMember(id=u.id, name=u.name, email=u.email, designation=u.designation) for u in sample],
    )


@router.get("/{group_id}/members", response_model=GroupMembersResponse)
def view_group_members(
    group_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Full resolved membership for an already-saved group — the 'View
    Members' page/modal, as opposed to the 5-name sample the builder shows
    while a group's rules are still being edited (see /preview above)."""
    group = _load_group(db, group_id)
    try:
        members = list_group_members(db, group)
    except InvalidRuleError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return GroupMembersResponse(
        total=len(members),
        members=[
            GroupMember(id=u.id, name=u.name, email=u.email, cpf=u.cpf, designation=u.designation)
            for u in members
        ],
    )


# ── Course <-> Group targeting ───────────────────────────────────────────────
# Mirrors admin/courses.py's target-user endpoints (list/add/remove), just
# for a whole group at a time instead of one individual employee.

def _load_course(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


@router.get("/course-targets/{course_id}", response_model=List[CourseTargetGroupRead])
def list_course_target_groups(
    course_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    _load_course(db, course_id)
    rows = (
        db.query(CourseTargetGroup)
        .options(joinedload(CourseTargetGroup.group).joinedload(EmployeeGroup.rules))
        .filter(CourseTargetGroup.course_id == course_id)
        .all()
    )
    out = []
    for row in rows:
        try:
            count = count_group_members(db, row.group)
        except InvalidRuleError:
            count = 0
        out.append(CourseTargetGroupRead(id=row.id, group_id=row.group_id, group_name=row.group.name, member_count=count))
    return out


@router.post("/course-targets/{course_id}", response_model=CourseTargetGroupRead, status_code=201,
             dependencies=[Depends(verify_csrf)])
def add_course_target_group(
    course_id: int,
    body: CourseTargetGroupCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    _load_course(db, course_id)
    group = _load_group(db, body.group_id)

    row = CourseTargetGroup(course_id=course_id, group_id=body.group_id)
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This group is already targeted at this course")
    audit(db, actor_id=actor.id, action="add_course_target_group", target_type="course_target_group",
          target_id=row.id, detail={"course_id": course_id, "group_id": body.group_id})
    db.commit()
    try:
        count = count_group_members(db, group)
    except InvalidRuleError:
        count = 0
    return CourseTargetGroupRead(id=row.id, group_id=group.id, group_name=group.name, member_count=count)


@router.delete("/course-targets/{course_id}/{target_group_id}", status_code=204,
                dependencies=[Depends(verify_csrf)])
def remove_course_target_group(
    course_id: int,
    target_group_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    row = db.query(CourseTargetGroup).filter(
        CourseTargetGroup.id == target_group_id,
        CourseTargetGroup.course_id == course_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(row)
    audit(db, actor_id=actor.id, action="remove_course_target_group", target_type="course_target_group",
          target_id=target_group_id, detail={"course_id": course_id})
    db.commit()
