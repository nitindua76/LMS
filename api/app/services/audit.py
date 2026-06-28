from typing import Optional, Any
from sqlalchemy.orm import Session
from app.models.audit import AuditLog


def audit(
    db: Session,
    *,
    actor_id: Optional[int],
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[Any] = None,
    detail: Optional[dict] = None,
) -> AuditLog:
    """Write one row to audit_logs. Call this for every significant mutation."""
    log = AuditLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        detail=detail,
    )
    db.add(log)
    db.flush()
    return log
