from fastapi import Cookie, Header, HTTPException, status, Request, Depends
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.user import User, UserRole
from app.services import auth as auth_svc
from app.services.redis_client import get_redis


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Reads the access token from httpOnly cookie, validates, returns User."""
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = auth_svc.decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    user_id = int(payload["sub"])
    user = db.get(User, user_id)
    if not user or not user.active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or deactivated",
        )
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


def require_employee(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.employee:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Employee access only"
        )
    return current_user


def verify_csrf(
    request: Request,
    x_csrf_token: Optional[str] = Header(None, alias="X-CSRF-Token"),
) -> None:
    """Double-submit cookie CSRF check for all state-changing requests."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    cookie_csrf = request.cookies.get("csrf_token")
    if not cookie_csrf or not x_csrf_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing CSRF token")
    if not _constant_time_compare(cookie_csrf, x_csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")


def _constant_time_compare(a: str, b: str) -> bool:
    import hmac
    return hmac.compare_digest(a, b)
