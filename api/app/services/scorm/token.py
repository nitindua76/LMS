"""Short-lived SCORM session tokens (separate secret from user JWTs)."""
import time
import uuid
import jwt
from app.config import settings

_ALG = "HS256"


def create_scorm_token(
    user_id: int,
    package_id: int,
    enrollment_id: int,
    ttl: int = 3600,
) -> str:
    payload = {
        "sub":  str(user_id),
        "pkg":  package_id,
        "enr":  enrollment_id,
        "jti":  str(uuid.uuid4()),
        "exp":  int(time.time()) + ttl,
        "type": "scorm",
    }
    return jwt.encode(payload, settings.SCORM_TOKEN_SECRET, algorithm=_ALG)


def decode_scorm_token(token: str) -> dict:
    """Raises jwt.PyJWTError on invalid/expired token."""
    return jwt.decode(token, settings.SCORM_TOKEN_SECRET, algorithms=[_ALG])
