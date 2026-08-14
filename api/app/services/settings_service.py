"""
DB-first, env-var-fallback runtime settings (see models/system_setting.py
for why this table exists at all — the short version: SSO/Employee API
endpoints and the Instant Rooms kill switch need to be admin-editable
without a redeploy; everything else in the app stays plain env vars).
"""
from typing import Optional
from sqlalchemy.orm import Session

from app.models.system_setting import SystemSetting
from app.services.audit import audit


def get_setting(db: Session, key: str, default: str = "") -> str:
    """DB value if a row exists and is non-empty, else the caller-supplied
    default (normally the matching env var from config.py)."""
    row = db.get(SystemSetting, key)
    if row is not None and row.value is not None and row.value != "":
        return row.value
    return default


def get_setting_bool(db: Session, key: str, default: bool) -> bool:
    row = db.get(SystemSetting, key)
    if row is not None and row.value is not None and row.value != "":
        return row.value.strip().lower() in ("1", "true", "yes", "on")
    return default


def set_setting(db: Session, key: str, value: str, *, actor_id: Optional[int]) -> SystemSetting:
    row = db.get(SystemSetting, key)
    if row is None:
        row = SystemSetting(key=key, value=value, updated_by_id=actor_id)
        db.add(row)
    else:
        row.value = value
        row.updated_by_id = actor_id
    db.flush()
    audit(db, actor_id=actor_id, action="update_system_setting", target_type="system_setting",
          target_id=key, detail={"key": key})
    return row
