from pydantic import BaseModel, field_validator
from typing import Optional
from app.models.user import UserRole, AuthProvider


class LoginRequest(BaseModel):
    # Deliberately a plain string, not EmailStr — this is either a CPF
    # number (SSO-authenticated employees) or an email (existing
    # local-password accounts, kept as a break-glass path — see
    # AuthProvider in models/user.py). The auth router decides which by
    # looking up the identifier, not by its shape.
    identifier: str
    password: str

    @field_validator("identifier")
    @classmethod
    def identifier_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("identifier is required")
        return v


class MeResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    email: str
    cpf: Optional[str] = None
    auth_provider: AuthProvider
    role: UserRole
    discipline_id: Optional[int] = None
    level_id: Optional[int] = None
    active: bool
    force_password_change: bool
    can_create_rooms: bool


class TokenPayload(BaseModel):
    sub: str
    jti: str
    role: str
    exp: int
    type: str
