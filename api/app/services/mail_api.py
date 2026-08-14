"""
Auto-mail integration for sharing Instant Room meeting links.

Deliberately separate from services/mailer.py (the SMTP sender used by
session reminders) — this talks to a different, GET-based corporate mail
API that takes the whole message as query-string params, e.g.:

    https://appserver1.ongc.co.in:8089/MailApi/mail?mailid=someone@ongc.co.in
        &msg=LMS%20Automated%20Mail%20Service&subject=DISCUSSION%20LINK
        &template=LMS_LINK&templateparams=templateBody::<link>,,templateHeader::DISCUSSION%20LINK

MAIL_API_URL_TEMPLATE holds that whole URL verbatim, with placeholders
substituted at call time: {mailid} (the target's email), {link} (the
actual meeting join URL — the literal word "link" in the sample above is
replaced by this), and {name} (the room's display name, e.g. "Daily
standup" — usable in the subject/msg/templateparams so the recipient can
tell which room the link is for, since {link} alone is an opaque URL).
Admin-configurable via the Settings page since the exact template (query
param names, `template=` value, static message text) is
deployment-specific, not something to hardcode.
"""
import logging
from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.services.settings_service import get_setting

logger = logging.getLogger(__name__)

# The placeholder email domain _get_or_create_by_cpf (services/sso.py) uses
# for a not-yet-synced CPF placeholder — mailing this address would always
# bounce, so skip the call entirely rather than making a pointless request.
_PLACEHOLDER_EMAIL_SUFFIX = "@unresolved.ongc.co.in"


def send_meeting_link_email(db: Session, *, to_email: str, link: str, room_name: str = "") -> bool:
    """
    Best-effort, fire-and-forget: never raises. Returns True only if the
    call was actually attempted and returned a 2xx — False for "not
    configured", "placeholder email", or any transport/HTTP failure. Every
    call site treats False the same way: log and move on, never block the
    action that triggered the mail (adding a member must not fail just
    because this secondary system is slow or down).
    """
    if not to_email or to_email.lower().endswith(_PLACEHOLDER_EMAIL_SUFFIX):
        return False
    template = get_setting(db, "MAIL_API_URL_TEMPLATE", settings.MAIL_API_URL_TEMPLATE)
    if not template:
        return False

    url = (
        template
        .replace("{mailid}", quote(to_email, safe="@."))
        .replace("{link}", quote(link, safe=""))
        .replace("{name}", quote(room_name, safe=""))
    )
    timeout = float(get_setting(db, "MAIL_API_TIMEOUT_SECONDS", str(settings.MAIL_API_TIMEOUT_SECONDS)))
    try:
        resp = httpx.get(url, timeout=timeout)
        resp.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        logger.warning("Mail API call failed for %s: %s", to_email, exc)
        return False
