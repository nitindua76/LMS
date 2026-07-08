"""
Controlling-officer assignment — single source of truth for reading/writing
who controls whom.

`User.controller_id` always holds the current assignment (fast, indexed lookup
for authorization checks). `ControllerAssignmentHistory` is the audit trail
behind it: exactly one open row (effective_to is NULL) per user at a time.

The real HR/company API that resolves a user's controlling officer isn't
available yet. `ControllerSyncProvider` is the seam where that integration
plugs in later — swap `NullSyncProvider` for a real implementation without
touching `assign_controller` or any endpoint that reads `controller_id`.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.controller_history import ControllerAssignmentHistory, ControllerAssignmentSource
from app.services.audit import audit


class ControllerAssignmentError(Exception):
    """Raised when an assignment would be invalid (self-reference or a cycle)."""


class ControllerSyncProvider(ABC):
    """Resolves a user's controlling officer from an external system."""

    @abstractmethod
    def resolve_controller(self, user: User) -> Optional[User]:
        """Return the User who currently controls `user`, or None if unknown/unassigned."""
        raise NotImplementedError


class NullSyncProvider(ControllerSyncProvider):
    """Placeholder used until the company HR API is wired up. Resolves nothing,
    so the periodic sync job becomes a no-op and manual/admin assignment is
    authoritative in the meantime."""

    def resolve_controller(self, user: User) -> Optional[User]:
        return None


def get_direct_reports(db: Session, controller: User) -> List[User]:
    """Users currently reporting to `controller` (immediate reports only)."""
    return (
        db.query(User)
        .filter(User.controller_id == controller.id, User.active.is_(True))
        .order_by(User.name)
        .all()
    )


def is_controller_of(db: Session, controller: User, subordinate_id: int) -> bool:
    subordinate = db.get(User, subordinate_id)
    return subordinate is not None and subordinate.controller_id == controller.id


def _would_create_cycle(db: Session, user: User, new_controller: User) -> bool:
    """Walk up from `new_controller` — if we hit `user`, assigning it would form a cycle."""
    seen: set[int] = set()
    current: Optional[User] = new_controller
    while current is not None:
        if current.id == user.id:
            return True
        if current.id in seen:
            break  # already-broken cycle elsewhere; don't loop forever
        seen.add(current.id)
        current = db.get(User, current.controller_id) if current.controller_id else None
    return False


def assign_controller(
    db: Session,
    *,
    user: User,
    new_controller: Optional[User],
    source: ControllerAssignmentSource,
    actor_id: Optional[int] = None,
) -> User:
    """
    Set `user.controller_id`, closing the previous history row and opening a
    new one. Idempotent if the controller is unchanged. Raises
    ControllerAssignmentError on self-assignment or a cycle.
    """
    if new_controller is not None:
        if new_controller.id == user.id:
            raise ControllerAssignmentError("A user cannot control themselves")
        if _would_create_cycle(db, user, new_controller):
            raise ControllerAssignmentError("This assignment would create a reporting cycle")

    if user.controller_id == (new_controller.id if new_controller else None):
        return user

    now = datetime.now(timezone.utc)
    db.query(ControllerAssignmentHistory).filter(
        ControllerAssignmentHistory.user_id == user.id,
        ControllerAssignmentHistory.effective_to.is_(None),
    ).update({"effective_to": now})

    db.add(ControllerAssignmentHistory(
        user_id=user.id,
        controller_id=new_controller.id if new_controller else None,
        source=source,
        effective_from=now,
    ))

    old_controller_id = user.controller_id
    user.controller_id = new_controller.id if new_controller else None
    db.flush()

    audit(
        db, actor_id=actor_id, action="assign_controller", target_type="user",
        target_id=user.id,
        detail={
            "old_controller_id": old_controller_id,
            "new_controller_id": user.controller_id,
            "source": source.value,
        },
    )
    return user


def sync_controllers(db: Session, provider: ControllerSyncProvider, users: List[User]) -> int:
    """
    Periodic job entry point: resolve each user's controller via `provider`
    and apply any change. Returns the number of assignments actually changed.
    Invalid resolutions (self/cycle) are skipped, not raised, so one bad
    upstream record can't halt the whole sync run.
    """
    changed = 0
    for user in users:
        resolved = provider.resolve_controller(user)
        if resolved is None:
            continue
        if user.controller_id == resolved.id:
            continue
        try:
            assign_controller(
                db, user=user, new_controller=resolved,
                source=ControllerAssignmentSource.api_sync,
            )
            changed += 1
        except ControllerAssignmentError:
            continue
    return changed
