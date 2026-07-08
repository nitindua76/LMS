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

    # Rate limiting
    LOGIN_MAX_ATTEMPTS_PER_IP: int = 20
    LOGIN_WINDOW_SECONDS: int = 300
    ACCOUNT_MAX_ATTEMPTS: int = 10
    ACCOUNT_LOCKOUT_SECONDS: int = 900

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

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
