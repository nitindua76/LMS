"""
SSO (CPF+password authentication) and Employee API (hierarchy/profile sync)
integration.

Two genuinely separate upstream systems, deliberately kept independent:

  SsoClient           -> e.g. https://appserver1.ongc.co.in:8089/Employee/chkCredential
                         Answers exactly one question: is this CPF+password
                         combination valid? Nothing else. Never raises for a
                         normal "invalid credentials" result — only for
                         actual transport/protocol failures, which the
                         caller (auth router) treats as a 5xx, not a 401.

                         POST, with cpf/pwd sent BOTH as query-string params
                         (alongside a fixed `server` param, "AD" by default)
                         AND as a JSON body — that's the real contract this
                         endpoint expects, not a simplification on our end:

                           POST {base_url}?cpf=95257&pwd=***&server=AD
                           Content-Type: application/json
                           {"cpf": "95257", "pwd": "***"}

                         SSO_API_BASE_URL is the FULL endpoint URL including
                         the /Employee/chkCredential path (whatever the
                         admin pastes into the Settings page verbatim) — not
                         just a host, since the path isn't the same across
                         every environment this has been pointed at so far.

  EmployeeApiClient    -> e.g. https://appserver1.ongc.co.in:9696/EmployeeNew/GetFullDetails
                         Returns profile + hierarchy (CONTROLLING/L1/L2/
                         IC_HRER) for a CPF. Used to provision/refresh User
                         rows; login success never depends on this call
                         succeeding (see login_or_provision).

                         EMPLOYEE_API_BASE_URL is the FULL endpoint URL
                         (whatever the admin pastes into the Settings page
                         verbatim), same convention as SSO_API_BASE_URL —
                         NOT just a host with /EmployeeNew/GetFullDetails
                         appended on top (that was a real bug here: it
                         produced a doubled path like
                         ".../GetFullDetails/EmployeeNew/GetFullDetails",
                         which 404'd on every call and silently fell back to
                         "skip the sync", so logins never picked up real
                         Employee API details).

Both base URLs/keys are read through get_setting() (DB-first, env-var
fallback — see services/settings_service.py) so an admin can change them at
runtime without a redeploy.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.config import settings
from app.models.user import User, AuthProvider, UserRole
from app.schemas.employee_api import EmployeeDetails, EmployeeApiResponse
from app.services.controller import ControllerSyncProvider
from app.services.settings_service import get_setting


class SsoClient:
    """Talks to the CPF+password credential-check API. Stateless; construct
    fresh per call (or per request) rather than caching — base_url/timeout
    can change at runtime via admin settings."""

    def __init__(self, base_url: str, timeout: float, server: str = "AD"):
        # This is the FULL endpoint URL (e.g.
        # https://appserver1.ongc.co.in:8089/Employee/chkCredential), not
        # just a host — see the module docstring for why.
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._server = server or "AD"

    def authenticate(self, cpf: str, password: str) -> bool:
        """
        Returns True for a VALID result, False for INVALID. Never raises for
        a normal invalid-credentials result.

        The real endpoint's response body is a bare JSON string — e.g.
        `"VALID"` or `"INVALID"` (confirmed against the live API: a wrong
        password gets HTTP 202 with body '"INVALID"', not a 401/403 — the
        HTTP status code here is NOT meaningful, only the body is). Some
        deployments may instead wrap it as {"Message": "VALID"}, so that
        shape is also accepted defensively.

        Raises SsoUnavailableError only for actual transport failures
        (timeout, connection refused, non-2xx transport error, unparseable
        body) — the caller treats that as "can't verify right now", not
        "wrong password".
        """
        if not self._base_url:
            raise SsoUnavailableError("SSO_API_BASE_URL is not configured")
        try:
            resp = httpx.post(
                self._base_url,
                params={"cpf": cpf, "pwd": password, "server": self._server},
                json={"cpf": cpf, "pwd": password},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            body = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            # This used to be swallowed into a bare 503 with no trail —
            # log it so a misconfigured URL/cert/firewall issue shows up in
            # the API logs instead of just "temporarily unavailable" with
            # no way to tell why.
            logger.warning("SSO API request to %s failed: %s", self._base_url, exc)
            raise SsoUnavailableError(f"SSO API request failed: {exc}") from exc

        if isinstance(body, str):
            message = body
        elif isinstance(body, dict):
            message = body.get("Message", "")
        else:
            message = ""
        return str(message).strip().upper() == "VALID"


class SsoUnavailableError(Exception):
    """The SSO API could not be reached or returned something unparseable —
    distinct from a normal INVALID credential result."""


class EmployeeApiClient:
    """Talks to the Employee API for profile + hierarchy details."""

    def __init__(self, base_url: str, api_key: str, timeout: float):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def get_full_details(self, cpf: str) -> Optional[EmployeeDetails]:
        """
        Returns None if the employee isn't found or the API is unreachable —
        deliberately swallows transport errors here rather than raising,
        because every call site treats "couldn't fetch details" the same
        way: skip the sync, keep whatever's already in the DB. Login/CPF-add
        flows must not fail just because this secondary system is slow or
        down.
        """
        if not self._base_url or not self._api_key:
            return None
        try:
            resp = httpx.get(
                self._base_url,
                params={"cpf": cpf, "apiKey": self._api_key},
                timeout=self._timeout,
            )
            resp.raise_for_status()
            parsed = EmployeeApiResponse.model_validate(resp.json())
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Employee API lookup failed for cpf=%s: %s", cpf, exc)
            return None
        return parsed.employeelist[0] if parsed.employeelist else None


def get_sso_client(db: Session) -> SsoClient:
    return SsoClient(
        base_url=get_setting(db, "SSO_API_BASE_URL", settings.SSO_API_BASE_URL),
        timeout=float(get_setting(db, "SSO_API_TIMEOUT_SECONDS", str(settings.SSO_API_TIMEOUT_SECONDS))),
        server=get_setting(db, "SSO_SERVER", settings.SSO_SERVER),
    )


def get_employee_api_client(db: Session) -> EmployeeApiClient:
    return EmployeeApiClient(
        base_url=get_setting(db, "EMPLOYEE_API_BASE_URL", settings.EMPLOYEE_API_BASE_URL),
        api_key=get_setting(db, "EMPLOYEE_API_KEY", settings.EMPLOYEE_API_KEY),
        timeout=float(get_setting(db, "EMPLOYEE_API_TIMEOUT_SECONDS", str(settings.EMPLOYEE_API_TIMEOUT_SECONDS))),
    )


def _apply_employee_fields(user: User, details: EmployeeDetails) -> None:
    """Overwrite the denormalized profile fields from a fresh API response.
    Never touches role/discipline_id/level_id/active/can_create_rooms —
    those are LMS-side concepts the Employee API knows nothing about."""
    if details.mail:
        user.email = details.mail.lower().strip()
    user.name = details.name.strip()
    user.designation = details.designation
    user.mobile = details.mobile
    user.posting = details.posting
    user.location = details.location
    user.gender = details.gender
    user.birth_date = details.birth_date
    user.valid_upto = details.valid_upto
    user.is_retired = details.is_retired
    user.last_synced_at = datetime.now(timezone.utc)
    # A retired employee should not remain logged-in-capable — mirrors the
    # existing deactivate_user path (admin/users.py) but driven by upstream
    # data instead of a manual admin click.
    if details.is_retired and user.active:
        user.active = False


def _get_or_create_by_cpf(db: Session, cpf: str, fallback_name: str = "") -> User:
    """
    Look up a User by CPF. If none exists, create a minimal placeholder row
    (auth_provider=sso, no password, no email yet) rather than raising — the
    caller fills in real details via _apply_employee_fields once it has them.
    This is what lets CPF-add-to-a-course/room/group work for someone who
    has never logged in and whose Employee API record hasn't been fetched
    yet at the point they're being added.
    """
    user = db.query(User).filter(User.cpf == cpf).first()
    if user:
        return user
    # placeholder email — unique, never shown, overwritten by the first
    # successful Employee API sync (users.email is NOT NULL + unique, so
    # this can't be left blank)
    user = User(
        name=fallback_name or f"Employee {cpf}",
        email=f"cpf-{cpf}@unresolved.ongc.co.in",
        password_hash=None,
        role=UserRole.employee,
        auth_provider=AuthProvider.sso,
        cpf=cpf,
    )
    db.add(user)
    db.flush()
    return user


def upsert_user_from_employee_details(db: Session, details: EmployeeDetails) -> User:
    """
    The shared provisioning primitive: given one EmployeeDetails record,
    ensure a User row exists for its CPF (creating or reattaching-by-email
    as needed), refresh its denormalized profile fields, and recursively
    upsert+wire CONTROLLING/L1/L2/IC_HRER (one level each, not their own
    subordinates — the recursion in this call already reaches those tiers
    for the same person, so following each of *their* sub-hierarchies too
    would fan out unboundedly from a single login).

    Called from:
      - services/sso.py::sync_employee_details_background (post-login sync,
        scheduled as a background task by routers/auth.py — never inline)
      - the periodic EmployeeApiControllerSyncProvider job
      - CPF-add flows (courses/groups/rooms) for a not-yet-registered CPF
    """
    user = _reattach_or_create(db, details)
    _apply_employee_fields(user, details)

    if details.controlling is not None:
        controller = upsert_user_from_employee_details(db, details.controlling)
        if controller.id != user.id:
            user.controller_id = controller.id
    if details.l1 is not None:
        l1 = upsert_user_from_employee_details(db, details.l1)
        if l1.id != user.id:
            user.l1_id = l1.id
    if details.l2 is not None:
        l2 = upsert_user_from_employee_details(db, details.l2)
        if l2.id != user.id:
            user.l2_id = l2.id
    if details.ic_hrer is not None:
        ic = upsert_user_from_employee_details(db, details.ic_hrer)
        if ic.id != user.id:
            user.ic_hrer_id = ic.id

    db.flush()
    return user


def _reattach_or_create(db: Session, details: EmployeeDetails) -> User:
    """
    By CPF first. If not found and this person already has a User row from
    before SSO existed (matched by email), attach the CPF to that existing
    row instead of creating a duplicate account with separate history.
    """
    user = db.query(User).filter(User.cpf == details.cpf).first()
    if user:
        return user
    if details.mail:
        email = details.mail.lower().strip()
        existing = db.query(User).filter(User.email == email).first()
        if existing and existing.cpf is None:
            existing.cpf = details.cpf
            return existing
    return _get_or_create_by_cpf(db, details.cpf, fallback_name=details.name)


def login_or_provision(
    db: Session,
    *,
    cpf: str,
    password: str,
    sso_client: SsoClient,
) -> User:
    """
    The auth router's entry point for CPF-based login. Raises
    SsoAuthenticationError for wrong credentials (mapped to 401 by the
    caller) or SsoUnavailableError if the upstream itself couldn't be
    reached (mapped to 503 — this is NOT "wrong password", and must not be
    treated as one for rate-limiting purposes).

    Deliberately does NOT call the Employee API here — that sync always
    still happens (per the "call it after every credential check, no
    exceptions" requirement), but as a background task the auth router
    kicks off AFTER this returns (see sync_employee_details_background),
    so a slow upstream (the real one observed: a consistent multi-second
    response time on this deployment's Employee API host, occasionally 6-
    10s) adds zero perceived delay to signing in. The credential check
    itself is a separate, much faster upstream call and stays fully
    synchronous — that's the one thing that must complete before a session
    can be issued at all.
    """
    if not sso_client.authenticate(cpf, password):
        raise SsoAuthenticationError("Invalid CPF or password")

    user = db.query(User).filter(User.cpf == cpf).first()
    if user is None:
        user = _get_or_create_by_cpf(db, cpf)

    if user.auth_provider != AuthProvider.sso:
        user.auth_provider = AuthProvider.sso
    db.flush()
    return user


def sync_employee_details_background(cpf: str) -> None:
    """
    Runs the Employee API fetch + upsert on its own DB session, meant to be
    scheduled via FastAPI's BackgroundTasks (executes after the HTTP
    response has already been sent) or a periodic job — never called
    inline during the login request itself. See login_or_provision's
    docstring for why this split exists.
    """
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        client = get_employee_api_client(db)
        details = client.get_full_details(cpf)
        if details is not None:
            upsert_user_from_employee_details(db, details)
            db.commit()
    except Exception:
        logger.exception("Background Employee API sync failed for cpf=%s", cpf)
        db.rollback()
    finally:
        db.close()


class SsoAuthenticationError(Exception):
    """CPF+password combination was rejected by the SSO API (normal invalid
    login, not a transport failure)."""


class EmployeeApiControllerSyncProvider(ControllerSyncProvider):
    """
    Real implementation of the seam controller.py already anticipated —
    resolves a user's controlling officer via the Employee API instead of
    NullSyncProvider's no-op. Used by the existing sync_controllers() job
    unchanged; nothing that reads User.controller_id needs to know this
    provider exists.
    """

    def __init__(self, db: Session, client: EmployeeApiClient):
        self._db = db
        self._client = client

    def resolve_controller(self, user: User) -> Optional[User]:
        if not user.cpf:
            return None
        details = self._client.get_full_details(user.cpf)
        if details is None or details.controlling is None:
            return None
        return upsert_user_from_employee_details(self._db, details.controlling)
