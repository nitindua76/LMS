from pydantic_settings import BaseSettings
from pydantic import AnyUrl, field_validator
from typing import List


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+psycopg://lms:lmspassword@localhost:5437/lms"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET: str
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Cookies
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    COOKIE_DOMAIN: str = ""

    # CORS
    CORS_ORIGINS: str = "http://lms.local:5173"

    # Environment
    ENVIRONMENT: str = "development"

    # Storage backend: "minio" (default, for Docker Compose / on-prem / S3) or "local" (dev without MinIO)
    STORAGE_BACKEND: str = "minio"
    STORAGE_LOCAL_PATH: str = "/data/storage"

    # Content upload caps, enforced server-side while streaming (not just Content-Length)
    MAX_VIDEO_UPLOAD_MB: int = 500
    MAX_PDF_UPLOAD_MB: int = 25

    # MinIO / Object Storage (used when STORAGE_BACKEND=minio)
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "lmsadmin"
    MINIO_SECRET_KEY: str = "lmspassword"
    MINIO_BUCKET: str = "lms-packages"
    MINIO_SECURE: bool = False

    # Content origin (separate origin for SCORM/cmi5 package serving)
    CONTENT_ORIGIN: str = "http://content.local:5174"

    # The URL the browser uses to reach the API — used in SCORM/cmi5 launch URLs
    # that are opened at the content origin, so they cannot go through the Vite proxy.
    API_EXTERNAL_URL: str = "http://lms.local:8000"

    # LRS (xAPI) — leave blank to skip forwarding in dev
    LRS_ENDPOINT: str = ""
    LRS_USERNAME: str = ""
    LRS_PASSWORD: str = ""

    # SCORM session token (separate from user JWT)
    SCORM_TOKEN_SECRET: str = "dev-scorm-secret-replace-in-production"

    # LiveKit (self-hosted) — LIVEKIT_URL is the wss:// address the browser
    # connects to; LIVEKIT_SERVER_URL is how the api container reaches the
    # Room Service API (usually the same host, http(s):// scheme) and may
    # differ from LIVEKIT_URL when the api talks to it over the compose
    # network directly instead of through the public reverse proxy.
    LIVEKIT_URL: str = "ws://localhost:7880"
    LIVEKIT_SERVER_URL: str = "http://localhost:7880"
    LIVEKIT_API_KEY: str = "devkey"
    LIVEKIT_API_SECRET: str = "dev-livekit-secret-replace-in-production"
    # Minimum minutes of a session's scheduled duration an attendee must be
    # present for (cumulative, across rejoins) before it counts as attended
    # for completion purposes.
    SESSION_ATTENDANCE_COMPLETION_PCT: int = 60

    # SMTP (session reminder emails) — points at the Mailpit dev container by default
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_FROM: str = "lms@example.com"

    # Rate limiting
    LOGIN_MAX_ATTEMPTS_PER_IP: int = 20
    LOGIN_WINDOW_SECONDS: int = 300
    ACCOUNT_MAX_ATTEMPTS: int = 10
    ACCOUNT_LOCKOUT_SECONDS: int = 900

    # ── SSO / Employee API (see services/sso.py) ────────────────────────────
    # These are the fallback/dev defaults only — an admin can override every
    # one of these at runtime via the system_settings table (see
    # services/settings_service.py) without a redeploy. Blank SSO_API_BASE_URL
    # disables SSO login entirely (local-password accounts still work).
    SSO_API_BASE_URL: str = ""
    SSO_API_TIMEOUT_SECONDS: float = 8.0
    # The chkCredential endpoint takes a `server` query param identifying
    # which directory to check against — "AD" in every deployment seen so
    # far, but exposed as a setting rather than hardcoded in case that ever
    # changes.
    SSO_SERVER: str = "AD"
    EMPLOYEE_API_BASE_URL: str = ""
    EMPLOYEE_API_KEY: str = ""
    # Higher than SSO_API_TIMEOUT_SECONDS on purpose: this call now always
    # runs as a background task (see services/sso.py's
    # sync_employee_details_background), never inline during login, so a
    # slow response here no longer costs the user anything — better to
    # give this upstream (observed taking anywhere from ~300ms to 10s+ on
    # this deployment) room to finish than time out and skip a sync that
    # would otherwise have succeeded.
    EMPLOYEE_API_TIMEOUT_SECONDS: float = 15.0
    # Whether a successful SSO login schedules an Employee API profile sync
    # at all. On by default — the sync itself always runs as a background
    # task (see routers/auth.py + services/sso.py's
    # sync_employee_details_background), never inline, so this flag is
    # purely "sync or don't", not "block or don't block" login.
    EMPLOYEE_SYNC_ON_LOGIN: bool = True
    # Local email+password login stays available even when SSO is
    # configured — deliberate break-glass path, see AuthProvider in
    # models/user.py.
    ENABLE_LOCAL_LOGIN_FALLBACK: bool = True

    # ── Instant Rooms (see models/instant_room.py) ──────────────────────────
    INSTANT_ROOMS_ENABLED: bool = True
    # The browser-facing base URL for this app — used to build the
    # shareable "join this room" link (copy-link button + auto-mail-on-
    # invite). Never localhost, same reasoning as LIVEKIT_HOST: this has to
    # be a hostname/IP a recipient's own browser can actually reach.
    FRONTEND_URL: str = "http://lms.local:5173"

    # ── Meeting-link auto-mail (see services/mail_api.py) ───────────────────
    # The corporate mail API's full URL, with {mailid}, {link}, and {name}
    # as literal placeholders substituted at send time: {mailid} becomes
    # the ADDED MEMBER's own email (never the room owner's), {link} becomes
    # the actual meeting join URL, {name} becomes the room's display name
    # (e.g. "Daily standup") so the subject/body can identify which room
    # the link is for. Defaults to the exact template ONGC's MailApi/mail
    # endpoint documented — override via the admin Settings page if the
    # deployment differs. Blank disables auto-mail entirely (copy-link
    # still works either way).
    MAIL_API_URL_TEMPLATE: str = (
        "https://appserver1.ongc.co.in:8089/MailApi/mail"
        "?mailid={mailid}&msg=LMS%20Automated%20Mail%20Service&subject={name}%20DISCUSSION%20LINK"
        "&template=LMS_LINK&templateparams=templateBody::{link},,templateHeader::{name}%20DISCUSSION%20LINK"
    )
    MAIL_API_TIMEOUT_SECONDS: float = 8.0

    @property
    def cors_origins_list(self) -> List[str]:
        # CORS matching is exact-string (scheme + host + port), so a stray
        # trailing slash here would silently make every preflight fail —
        # normalize instead of trusting whatever ends up in .env.
        return [o.strip().rstrip("/") for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def access_token_expire_seconds(self) -> int:
        return self.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60

    @property
    def refresh_token_expire_seconds(self) -> int:
        return self.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
