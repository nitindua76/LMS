import time
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, verify_csrf
from app.models.user import User, AuthProvider
from app.schemas.auth import LoginRequest, MeResponse
from app.services import auth as auth_svc
from app.services import sso as sso_svc
from app.services.audit import audit
from app.services.redis_client import get_redis
from app.services.settings_service import get_setting, get_setting_bool
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


def _looks_like_email(identifier: str) -> bool:
    return "@" in identifier


@router.post("/login", response_model=MeResponse)
def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    r = get_redis()
    client_ip = request.client.host if request.client else "unknown"

    if auth_svc.check_rate_limit_ip(client_ip, r):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts from this IP. Try again later.",
        )

    identifier = body.identifier.strip()
    # Rate limiting is keyed on whatever was typed (email or CPF) — the
    # existing per-identifier lockout logic in services/auth.py doesn't
    # care which kind of string it is, only that repeated failures against
    # the same one get locked out.
    rate_limit_key = identifier.lower()
    if auth_svc.check_rate_limit_email(rate_limit_key, r):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Account temporarily locked due to too many failed attempts.",
        )

    # Routing: an email-shaped identifier matching an existing
    # auth_provider=local account uses the original password path
    # unchanged (this is the deliberate break-glass fallback — see
    # AuthProvider in models/user.py). Everything else is treated as a CPF
    # and goes through SSO. A CPF that doesn't resolve to an existing user
    # yet is still routed to SSO — that's the normal first-ever-login case.
    user: User | None = None
    if _looks_like_email(identifier):
        candidate = db.query(User).filter(User.email == identifier.lower()).first()
        if candidate is not None and candidate.auth_provider == AuthProvider.local:
            user = candidate

    if user is not None:
        password_ok = auth_svc.verify_password(user.password_hash, body.password)
        if not password_ok:
            _record_login_failure(db, user, identifier, client_ip)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    else:
        if not get_setting_bool(db, "ENABLE_LOCAL_LOGIN_FALLBACK", settings.ENABLE_LOCAL_LOGIN_FALLBACK) \
                and not get_setting(db, "SSO_API_BASE_URL", settings.SSO_API_BASE_URL):
            # Neither auth path is actually configured — a real misconfig,
            # not a credentials problem, so this is a 503, not a 401.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Sign-in is not configured. Contact your administrator.",
            )
        try:
            user = sso_svc.login_or_provision(
                db,
                cpf=identifier,
                password=body.password,
                sso_client=sso_svc.get_sso_client(db),
            )
        except sso_svc.SsoAuthenticationError:
            _record_login_failure(db, None, identifier, client_ip)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid CPF or password")
        except sso_svc.SsoUnavailableError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Sign-in service is temporarily unavailable. Please try again shortly.",
            )
        # Employee API sync ALWAYS still runs after every successful
        # credential check (per requirement) — but as a background task,
        # not inline, since that upstream has been observed taking 4-10s+
        # on this deployment while the credential check itself takes
        # ~50-100ms. Running it inline would make every login as slow as
        # the slower of the two calls; this way login latency tracks only
        # the fast one.
        if get_setting_bool(db, "EMPLOYEE_SYNC_ON_LOGIN", settings.EMPLOYEE_SYNC_ON_LOGIN):
            background_tasks.add_task(sso_svc.sync_employee_details_background, identifier)

    if not user.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")

    auth_svc.reset_rate_limit(rate_limit_key, client_ip, r)

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
        detail={"ip": client_ip, "auth_provider": user.auth_provider.value},
    )
    db.commit()
    return user


def _record_login_failure(db: Session, user: User | None, identifier: str, client_ip: str) -> None:
    audit(
        db,
        actor_id=user.id if user else None,
        action="login_failed",
        target_type="user",
        target_id=identifier,
        detail={"ip": client_ip},
    )
    db.commit()


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
