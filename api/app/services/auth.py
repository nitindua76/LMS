import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
import redis

from app.config import settings

_ph = PasswordHasher(
    time_cost=2,
    memory_cost=65536,
    parallelism=2,
)

# Redis key patterns
REFRESH_TOKEN_KEY = "rt:{jti}"
USER_REFRESH_SET_KEY = "urt:{user_id}"
RATE_IP_KEY = "rl:ip:{ip}"
RATE_EMAIL_KEY = "rl:email:{email}"
LOCKOUT_IP_KEY = "lo:ip:{ip}"
LOCKOUT_EMAIL_KEY = "lo:email:{email}"


# ── Password ───────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        _ph.verify(password_hash, password)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# ── JWT ────────────────────────────────────────────────────────────────────────

def _make_token(user_id: int, role: str, token_type: str, expire_seconds: int) -> tuple[str, str]:
    """Returns (encoded_token, jti)."""
    jti = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "jti": jti,
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + timedelta(seconds=expire_seconds),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")
    return token, jti


def create_access_token(user_id: int, role: str) -> str:
    token, _ = _make_token(user_id, role, "access", settings.access_token_expire_seconds)
    return token


def create_refresh_token(user_id: int, role: str, r: redis.Redis) -> tuple[str, str]:
    """Creates refresh token, stores JTI in Redis. Returns (token, jti)."""
    token, jti = _make_token(user_id, role, "refresh", settings.refresh_token_expire_seconds)
    pipe = r.pipeline()
    pipe.setex(
        REFRESH_TOKEN_KEY.format(jti=jti),
        settings.refresh_token_expire_seconds,
        str(user_id),
    )
    pipe.sadd(USER_REFRESH_SET_KEY.format(user_id=user_id), jti)
    pipe.expire(
        USER_REFRESH_SET_KEY.format(user_id=user_id),
        settings.refresh_token_expire_seconds,
    )
    pipe.execute()
    return token, jti


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def revoke_refresh_token(jti: str, user_id: int, r: redis.Redis) -> None:
    pipe = r.pipeline()
    pipe.delete(REFRESH_TOKEN_KEY.format(jti=jti))
    pipe.srem(USER_REFRESH_SET_KEY.format(user_id=user_id), jti)
    pipe.execute()


def revoke_all_user_refresh_tokens(user_id: int, r: redis.Redis) -> None:
    """Used when deactivating a user — kills all their active sessions."""
    set_key = USER_REFRESH_SET_KEY.format(user_id=user_id)
    jtis = r.smembers(set_key)
    if jtis:
        pipe = r.pipeline()
        for jti in jtis:
            pipe.delete(REFRESH_TOKEN_KEY.format(jti=jti))
        pipe.delete(set_key)
        pipe.execute()


def is_refresh_token_valid(jti: str, user_id: int, r: redis.Redis) -> bool:
    stored = r.get(REFRESH_TOKEN_KEY.format(jti=jti))
    return stored == str(user_id)


# ── CSRF ───────────────────────────────────────────────────────────────────────

def generate_csrf_token() -> str:
    return secrets.token_hex(32)


# ── Rate limiting ──────────────────────────────────────────────────────────────

def check_rate_limit_ip(ip: str, r: redis.Redis) -> bool:
    """Returns True if IP is locked out."""
    if r.exists(LOCKOUT_IP_KEY.format(ip=ip)):
        return True
    count = r.incr(RATE_IP_KEY.format(ip=ip))
    if count == 1:
        r.expire(RATE_IP_KEY.format(ip=ip), settings.LOGIN_WINDOW_SECONDS)
    if count > settings.LOGIN_MAX_ATTEMPTS_PER_IP:
        r.setex(LOCKOUT_IP_KEY.format(ip=ip), settings.LOGIN_WINDOW_SECONDS, "1")
        return True
    return False


def check_rate_limit_email(email: str, r: redis.Redis) -> bool:
    """Returns True if account is locked out."""
    email_key = email.lower()
    if r.exists(LOCKOUT_EMAIL_KEY.format(email=email_key)):
        return True
    count = r.incr(RATE_EMAIL_KEY.format(email=email_key))
    if count == 1:
        r.expire(RATE_EMAIL_KEY.format(email=email_key), settings.LOGIN_WINDOW_SECONDS)
    if count > settings.ACCOUNT_MAX_ATTEMPTS:
        r.setex(LOCKOUT_EMAIL_KEY.format(email=email_key), settings.ACCOUNT_LOCKOUT_SECONDS, "1")
        return True
    return False


def reset_rate_limit(email: str, ip: str, r: redis.Redis) -> None:
    email_key = email.lower()
    pipe = r.pipeline()
    pipe.delete(RATE_EMAIL_KEY.format(email=email_key))
    pipe.delete(LOCKOUT_EMAIL_KEY.format(email=email_key))
    pipe.delete(RATE_IP_KEY.format(ip=ip))
    pipe.execute()
