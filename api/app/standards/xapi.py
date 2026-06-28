"""
xAPI statement builder and LRS forwarder.

All learning events funnel through emit(). Local xapi_statements table is the
source of truth — written unconditionally. LRS forwarding fires when LRS_ENDPOINT
is configured, with up to 3 attempts and exponential back-off.
"""
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.xapi import XapiStatement
from app.models.user import User

XAPI_VERSION = "1.0.3"
_RETRY_DELAYS = (1.0, 3.0, 9.0)   # seconds between attempts (3 total)

VERBS: dict[str, dict] = {
    "launched":    {"id": "http://adlnet.gov/expapi/verbs/launched",    "display": {"en-US": "launched"}},
    "initialized": {"id": "http://adlnet.gov/expapi/verbs/initialized", "display": {"en-US": "initialized"}},
    "completed":   {"id": "http://adlnet.gov/expapi/verbs/completed",   "display": {"en-US": "completed"}},
    "passed":      {"id": "http://adlnet.gov/expapi/verbs/passed",      "display": {"en-US": "passed"}},
    "failed":      {"id": "http://adlnet.gov/expapi/verbs/failed",      "display": {"en-US": "failed"}},
    "experienced": {"id": "http://adlnet.gov/expapi/verbs/experienced", "display": {"en-US": "experienced"}},
    "answered":    {"id": "http://adlnet.gov/expapi/verbs/answered",    "display": {"en-US": "answered"}},
    "scored":      {"id": "http://adlnet.gov/expapi/verbs/scored",      "display": {"en-US": "scored"}},
    "terminated":  {"id": "http://adlnet.gov/expapi/verbs/terminated",  "display": {"en-US": "terminated"}},
    "progressed":  {"id": "http://adlnet.gov/expapi/verbs/progressed",  "display": {"en-US": "progressed"}},
    "abandoned":   {"id": "https://w3id.org/xapi/adl/verbs/abandoned",  "display": {"en-US": "abandoned"}},
    "satisfied":   {"id": "https://w3id.org/xapi/adl/verbs/satisfied",  "display": {"en-US": "satisfied"}},
}


def _actor(user: User) -> dict:
    return {
        "objectType": "Agent",
        "name": user.name,
        "mbox": f"mailto:{user.email}",
    }


def _activity(iri: str, name: str, type_iri: str) -> dict:
    return {
        "objectType": "Activity",
        "id": iri,
        "definition": {
            "name": {"en-US": name},
            "type": type_iri,
        },
    }


def emit(
    db: Session,
    user: User,
    verb_key: str,
    activity_iri: str,
    activity_name: str,
    activity_type: str = "http://adlnet.gov/expapi/activities/course",
    result: Optional[dict] = None,
    context: Optional[dict] = None,
    enrollment_id: Optional[int] = None,
    statement_id: Optional[str] = None,
) -> XapiStatement:
    """
    Write one xAPI statement to the local table (always) and forward to the
    configured LRS (when LRS_ENDPOINT is set). Idempotent on statement_id.
    """
    sid = statement_id or str(uuid.uuid4())

    existing = db.query(XapiStatement).filter(XapiStatement.statement_id == sid).first()
    if existing:
        return existing

    stmt = XapiStatement(
        statement_id=sid,
        actor=_actor(user),
        verb=VERBS[verb_key],
        object=_activity(activity_iri, activity_name, activity_type),
        result=result,
        context=context,
        timestamp=datetime.now(timezone.utc),
        enrollment_id=enrollment_id,
        forwarded=False,
    )
    db.add(stmt)
    db.flush()

    if settings.LRS_ENDPOINT:
        _forward_with_retry(stmt)

    return stmt


def _forward_with_retry(stmt: XapiStatement) -> None:
    """
    POST to the configured LRS with up to 3 attempts (1s → 3s → 9s back-off).
    Populates stmt.forwarded / stmt.forwarded_at / stmt.lrs_response.
    Never raises — LRS errors must not abort the user's learning transaction.
    """
    payload = {
        "id":        stmt.statement_id,
        "actor":     stmt.actor,
        "verb":      stmt.verb,
        "object":    stmt.object,
        "timestamp": stmt.timestamp.isoformat(),
    }
    if stmt.result:
        payload["result"] = stmt.result
    if stmt.context:
        payload["context"] = stmt.context

    auth = (settings.LRS_USERNAME, settings.LRS_PASSWORD) if settings.LRS_USERNAME else None
    url  = f"{settings.LRS_ENDPOINT.rstrip('/')}/statements"
    headers = {
        "X-Experience-API-Version": XAPI_VERSION,
        "Content-Type": "application/json",
    }

    last_error: Optional[str] = None
    for attempt, delay in enumerate(_RETRY_DELAYS, start=1):
        try:
            r = httpx.post(url, json=payload, auth=auth, headers=headers, timeout=5.0)
            if r.status_code in (200, 204):
                stmt.forwarded = True
                stmt.forwarded_at = datetime.now(timezone.utc)
                stmt.lrs_response = {"status": r.status_code, "attempt": attempt}
                return
            last_error = f"HTTP {r.status_code}: {r.text[:200]}"
        except httpx.TransportError as exc:
            last_error = str(exc)

        if attempt < len(_RETRY_DELAYS):
            time.sleep(delay)

    # All attempts exhausted — mark as unforwarded so a background job can retry later
    stmt.forwarded = False
    stmt.lrs_response = {"error": last_error, "attempts": len(_RETRY_DELAYS)}
