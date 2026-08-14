"""
Admin-editable runtime settings — SSO/Employee API endpoints and the
Instant Rooms kill switch, the handful of things that genuinely need to be
changeable without a redeploy (see models/system_setting.py and
services/settings_service.py for why this table exists at all; everything
else in the app stays a plain env var).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin, verify_csrf
from app.models.user import User
from app.config import settings
from app.services.settings_service import get_setting, set_setting

router = APIRouter(prefix="/admin/settings", tags=["admin-settings"])

# Keys secret enough that the current value should never round-trip to the
# browser — the UI shows a placeholder and only overwrites the stored value
# when the admin actually types something new.
_SECRET_KEYS = {"EMPLOYEE_API_KEY"}

# (key, env default, is_bool) — the single source of truth for which
# settings this page exposes and what they fall back to when unset.
_SETTING_DEFS: List[tuple[str, str, bool]] = [
    ("SSO_API_BASE_URL", settings.SSO_API_BASE_URL, False),
    ("SSO_API_TIMEOUT_SECONDS", str(settings.SSO_API_TIMEOUT_SECONDS), False),
    ("SSO_SERVER", settings.SSO_SERVER, False),
    ("EMPLOYEE_API_BASE_URL", settings.EMPLOYEE_API_BASE_URL, False),
    ("EMPLOYEE_API_KEY", settings.EMPLOYEE_API_KEY, False),
    ("EMPLOYEE_API_TIMEOUT_SECONDS", str(settings.EMPLOYEE_API_TIMEOUT_SECONDS), False),
    ("EMPLOYEE_SYNC_ON_LOGIN", str(settings.EMPLOYEE_SYNC_ON_LOGIN), True),
    ("ENABLE_LOCAL_LOGIN_FALLBACK", str(settings.ENABLE_LOCAL_LOGIN_FALLBACK), True),
    ("INSTANT_ROOMS_ENABLED", str(settings.INSTANT_ROOMS_ENABLED), True),
    ("FRONTEND_URL", settings.FRONTEND_URL, False),
    ("MAIL_API_URL_TEMPLATE", settings.MAIL_API_URL_TEMPLATE, False),
    ("MAIL_API_TIMEOUT_SECONDS", str(settings.MAIL_API_TIMEOUT_SECONDS), False),
]


class SettingRead(BaseModel):
    key: str
    value: str
    is_bool: bool
    is_secret: bool
    is_set: bool  # False when this is still just the env-var default (nothing saved in the DB yet)


class SettingUpdate(BaseModel):
    value: str


@router.get("", response_model=List[SettingRead])
def list_settings(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    out = []
    for key, default, is_bool in _SETTING_DEFS:
        stored = get_setting(db, key, "")
        is_set = stored != ""
        value = stored if is_set else default
        if key in _SECRET_KEYS and value:
            value = "•" * 12  # never echo the real key back, set or not
        out.append(SettingRead(key=key, value=value, is_bool=is_bool, is_secret=key in _SECRET_KEYS, is_set=is_set))
    return out


@router.put("/{key}", response_model=SettingRead, dependencies=[Depends(verify_csrf)])
def update_setting(
    key: str,
    body: SettingUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    valid_keys = {k for k, _, _ in _SETTING_DEFS}
    if key not in valid_keys:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Unknown setting")

    new_value = body.value.strip()
    # A secret field left as the masked placeholder means "don't change it" —
    # the UI never has the real value to send back, so treat unchanged
    # dot-placeholder input as a no-op rather than overwriting a real key
    # with literal bullet characters.
    if key in _SECRET_KEYS and new_value and set(new_value) == {"•"}:
        stored = get_setting(db, key, "")
        is_set = stored != ""
        default = next(d for k, d, _ in _SETTING_DEFS if k == key)
        display = "•" * 12 if (stored or default) else ""
        return SettingRead(key=key, value=display, is_bool=False, is_secret=True, is_set=is_set)

    set_setting(db, key, new_value, actor_id=actor.id)
    db.commit()

    is_bool = next(b for k, _, b in _SETTING_DEFS if k == key)
    display = "•" * 12 if (key in _SECRET_KEYS and new_value) else new_value
    return SettingRead(key=key, value=display, is_bool=is_bool, is_secret=key in _SECRET_KEYS, is_set=new_value != "")
