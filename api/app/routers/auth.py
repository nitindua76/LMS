import time
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, verify_csrf
from app.models.user import User
from app.schemas.auth import LoginRequest, MeResponse
from app.services import auth as auth_svc
from app.services.audit import audit
from app.services.redis_client import get_redis
from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_OPTS = dict(
    httponly=True,
    secure=settings.COOKIE_SECURE,
    samesite=settings.COOKIE_SAMESITE,
    domain=settings.COOKIE_DOMAIN or None,
)


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str, csrf_token: str) -> None:
    response.set_cookie(
        "access_token",
        access_token,
        max_age=settings.access_token_expire_seconds,
        **COOKIE_OPTS,
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        max_age=settings.refresh_token_expire_seconds,
        **COOKIE_OPTS,
    )
    # CSRF cookie: NOT httpOnly so JS can read it
    response.set_cookie(
        "csrf_token",
        csrf_token,
        max_age=settings.refresh_token_expire_seconds,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        domain=settings.COOKIE_DOMAIN or None,
    )


def _clear_auth_cookies(response: Response) -> None:
    for name in ("access_token", "refresh_token", "csrf_token"):
        response.delete_cookie(name, **{k: v for k, v in COOKIE_OPTS.items() if k != "httponly"})


@router.post("/login", response_model=MeResponse)
def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    r = get_redis()
    client_ip = request.client.host if request.client else "unknown"

    # Rate limit checks before touching the DB
    if auth_svc.check_rate_limit_ip(client_ip, r):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts from this IP. Try again later.",
        )

    # Normalise email
    email = body.email.lower().strip()

    if auth_svc.check_rate_limit_email(email, r):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Account temporarily locked due to too many failed attempts.",
        )

    user = db.query(User).filter(User.email == email).first()

    # Constant-time: always run password verify to prevent timing oracle
    password_ok = user is not None and auth_svc.verify_password(user.password_hash, body.password)

    if not password_ok or user is None:
        audit(
            db,
            actor_id=user.id if user else None,
            action="login_failed",
            target_type="user",
            target_id=email,
            detail={"ip": client_ip},
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not user.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    auth_svc.reset_rate_limit(email, client_ip, r)

    access_token = auth_svc.create_access_token(user.id, user.role.value)
    refresh_token, _ = auth_svc.create_refresh_token(user.id, user.role.value, r)
    csrf_token = auth_svc.generate_csrf_token()

    _set_auth_cookies(response, access_token, refresh_token, csrf_token)

    audit(
        db,
        actor_id=user.id,
        action="login_success",
        target_type="user",
        target_id=user.id,
        detail={"ip": client_ip},
    )
    db.commit()
    return user


@router.post("/refresh", response_model=MeResponse, dependencies=[Depends(verify_csrf)])
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    payload = auth_svc.decode_token(token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = int(payload["sub"])
    jti = payload["jti"]

    r = get_redis()
    if not auth_svc.is_refresh_token_valid(jti, user_id, r):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revoked")

    user = db.get(User, user_id)
    if not user or not user.active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    # Rotate: revoke old, issue new
    auth_svc.revoke_refresh_token(jti, user_id, r)
    access_token = auth_svc.create_access_token(user.id, user.role.value)
    refresh_token, _ = auth_svc.create_refresh_token(user.id, user.role.value, r)
    csrf_token = auth_svc.generate_csrf_token()

    _set_auth_cookies(response, access_token, refresh_token, csrf_token)
    return user


@router.post("/logout", dependencies=[Depends(verify_csrf)])
def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    token = request.cookies.get("refresh_token")
    if token:
        payload = auth_svc.decode_token(token)
        if payload and payload.get("type") == "refresh":
            jti = payload["jti"]
            r = get_redis()
            auth_svc.revoke_refresh_token(jti, current_user.id, r)

    _clear_auth_cookies(response)
    audit(
        db,
        actor_id=current_user.id,
        action="logout",
        target_type="user",
        target_id=current_user.id,
    )
    db.commit()
    return {"message": "Logged out"}


@router.get("/me", response_model=MeResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user
