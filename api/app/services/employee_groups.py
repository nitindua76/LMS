"""
Dynamic employee group membership resolution — the core principle is that
membership is NEVER materialized/cached. A group is just a saved filter over
`users` columns; every call here re-runs that filter against live data, so a
transfer or a brand-new SSO-provisioned hire is picked up automatically with
no admin action and no batch job to keep in sync.

Rules within one group are AND-ed (see EmployeeGroupRule's docstring for why
zero rules matches nobody, not everybody). A course/room can target several
groups; that's an OR across groups, handled the same additive way
CourseTarget/CourseTargetUser already are in services/enrollment.py.
"""
from typing import List, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, Query

from app.models.user import User
from app.models.employee_group import EmployeeGroup, EmployeeGroupRule, RuleOperator

# Which User columns a rule is allowed to reference. Deliberately an
# allowlist, not "any attribute the ORM has" — this is the boundary between
# "safe filter target" and "arbitrary column admins could otherwise probe
# via trial and error" (e.g. password_hash must never be reachable here).
FIELD_MAP = {
    "discipline_id": User.discipline_id,
    "level_id": User.level_id,
    "posting": User.posting,
    "location": User.location,
    "designation": User.designation,
    "gender": User.gender,
    "role": User.role,
    "auth_provider": User.auth_provider,
    "controller_id": User.controller_id,
    "l1_id": User.l1_id,
    "l2_id": User.l2_id,
    "ic_hrer_id": User.ic_hrer_id,
}


class InvalidRuleError(Exception):
    pass


def _resolve_cpf_to_user_id(db: Session, cpf: str) -> Optional[int]:
    row = db.query(User.id).filter(User.cpf == cpf.strip()).first()
    return row[0] if row else None


def _subtree_user_ids(db: Session, root_id: int) -> set[int]:
    """
    Every user under root_id in the controller_id hierarchy, any depth —
    walked breadth-first in Python rather than a recursive SQL CTE, since
    ONGC-scale reporting trees are small enough (hundreds, not millions)
    that this is simpler to read and debug than a WITH RECURSIVE query, at
    a cost that's a non-issue at this scale.
    """
    seen: set[int] = set()
    frontier = [root_id]
    while frontier:
        rows = db.query(User.id).filter(User.controller_id.in_(frontier)).all()
        next_frontier = [r[0] for r in rows if r[0] not in seen]
        seen.update(next_frontier)
        frontier = next_frontier
    return seen


def _rule_condition(db: Session, rule: EmployeeGroupRule):
    """One SQLAlchemy filter expression for a single rule row."""
    if rule.operator in (RuleOperator.is_direct_report_of, RuleOperator.is_in_subtree_of):
        target_user_id = _resolve_cpf_to_user_id(db, rule.value)
        if target_user_id is None:
            # The referenced CPF doesn't resolve to any known user (yet) —
            # match nobody rather than raising, so one bad/stale rule
            # doesn't break the whole group's resolution for every other
            # rule combined with it.
            return User.id == -1
        if rule.operator == RuleOperator.is_direct_report_of:
            return User.controller_id == target_user_id
        subtree = _subtree_user_ids(db, target_user_id)
        return User.id.in_(subtree) if subtree else (User.id == -1)

    column = FIELD_MAP.get(rule.field)
    if column is None:
        raise InvalidRuleError(f"Unknown field: {rule.field}")

    # rule.value is always a plain string (it's a form field in the admin
    # UI), but several FIELD_MAP columns are integers (discipline_id,
    # level_id, controller_id/l1_id/l2_id/ic_hrer_id) — Postgres won't
    # implicitly compare integer = varchar, so those need an explicit cast
    # before building the condition. "contains" only makes sense for text
    # columns; used against one of the integer ones it's a user/API error.
    is_integer_field = rule.field in (
        "discipline_id", "level_id", "controller_id", "l1_id", "l2_id", "ic_hrer_id",
    )

    def _cast(raw: str):
        if not is_integer_field:
            return raw
        try:
            return int(raw)
        except ValueError:
            raise InvalidRuleError(f"'{rule.field}' requires a numeric value, got: {raw!r}")

    if rule.operator == RuleOperator.equals:
        return column == _cast(rule.value)
    if rule.operator == RuleOperator.contains:
        if is_integer_field:
            raise InvalidRuleError(f"'contains' is not valid for numeric field '{rule.field}'")
        return column.ilike(f"%{rule.value}%")
    if rule.operator == RuleOperator.in_list:
        values = [v.strip() for v in rule.value.split(",") if v.strip()]
        if not values:
            return User.id == -1
        return column.in_([_cast(v) for v in values])
    raise InvalidRuleError(f"Unknown operator: {rule.operator}")


def group_member_query(db: Session, group: EmployeeGroup) -> Query:
    """Base query for every active user matching every one of this group's
    rules. Callers add their own .filter()/.count()/.all() as needed."""
    q = db.query(User).filter(User.active.is_(True))
    if not group.rules:
        # No rules configured yet — deliberately matches nobody (see
        # EmployeeGroupRule's docstring). Cheapest way to express that
        # without a special case at every call site.
        return q.filter(User.id == -1)
    conditions = [_rule_condition(db, rule) for rule in group.rules]
    return q.filter(and_(*conditions))


def count_group_members(db: Session, group: EmployeeGroup) -> int:
    return group_member_query(db, group).count()


def user_matches_group(db: Session, user: User, group: EmployeeGroup) -> bool:
    return group_member_query(db, group).filter(User.id == user.id).first() is not None


def preview_group_members(db: Session, rules: List[dict], limit: int = 20) -> tuple[int, List[User]]:
    """
    Used by the admin builder UI before a group is saved — evaluates a
    candidate rule set (plain dicts: {field, operator, value} or
    {operator, value} for the CPF-based ones) without persisting anything,
    so an admin sees "N employees currently match" live while editing.
    Returns (total_count, sample_users[:limit]).
    """
    q = db.query(User).filter(User.active.is_(True))
    if not rules:
        return 0, []

    conditions = []
    for r in rules:
        fake_rule = EmployeeGroupRule(
            field=r.get("field", ""), operator=RuleOperator(r["operator"]), value=r["value"],
        )
        conditions.append(_rule_condition(db, fake_rule))
    q = q.filter(and_(*conditions))

    total = q.count()
    sample = q.order_by(User.name).limit(limit).all()
    return total, sample
