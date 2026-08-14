"""
Shared "resolve or provision a user by CPF" entry point — used by every
CPF-add flow in the app (course individual-targeting, Instant Room
membership, and indirectly by group rules that reference a CPF). One
implementation, not three copies.

Wraps services/sso.py's lower-level helpers rather than duplicating them:
if the user already exists (by CPF, or by email from a pre-SSO account),
returns it as-is; otherwise creates a minimal placeholder and — when an
EmployeeApiClient is supplied and reachable — immediately enriches it with
real profile/hierarchy data so a freshly CPF-added employee doesn't sit
around as "Employee 55257" until their first login.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.sso import EmployeeApiClient, _get_or_create_by_cpf, upsert_user_from_employee_details


def get_or_provision_by_cpf(
    db: Session, cpf: str, *, employee_client: Optional[EmployeeApiClient] = None
) -> User:
    cpf = cpf.strip()
    user = db.query(User).filter(User.cpf == cpf).first()
    if user is not None:
        return user

    if employee_client is not None:
        details = employee_client.get_full_details(cpf)
        if details is not None:
            return upsert_user_from_employee_details(db, details)

    return _get_or_create_by_cpf(db, cpf)
