from typing import Optional
from fastapi import FastAPI, Request, Query, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from app.config import settings
from app.routers.auth import router as auth_router
from app.routers.admin.disciplines import router as disciplines_router
from app.routers.admin.levels import router as levels_router
from app.routers.admin.users import router as users_router
from app.routers.admin.courses import router as courses_router
from app.routers.admin.sections import router as sections_router, content_router
from app.routers.admin.quizzes import router as quiz_router, questions_router, options_router
from app.routers.employee.courses import router as employee_courses_router
from app.routers.employee.team import router as employee_team_router
from app.routers.employee.content import router as employee_content_router
from app.routers.employee.scorm import router as scorm_router, launch_router as scorm_launch_router
from app.routers.employee.quiz import router as quiz_engine_router
from app.routers.employee.cmi5 import router as cmi5_router
from app.routers.admin.packages import router as packages_router
from app.routers.admin.analytics import router as analytics_router
from app.routers.admin.sessions import router as admin_sessions_router
from app.routers.employee.sessions import router as employee_sessions_router
from app.routers.webhooks.livekit import router as livekit_webhook_router

app = FastAPI(
    title="LMS API",
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
#
# Two distinct CORS policies:
#
# 1. Credential-bearing (main frontend at :5173 + any configured origins)
#    Used by the LMS UI — cookies are included so it gets Access-Control-Allow-Credentials.
#    The content origin (:5174) is DELIBERATELY excluded from this list so that
#    JavaScript running inside SCORM/cmi5 packages cannot make session-authenticated
#    requests to LMS employee endpoints.
#
# 2. No-credentials (content origin at CONTENT_ORIGIN)
#    Applies only to the SCORM/cmi5 runtime paths (/api/scorm/*, /api/cmi5/*).
#    The loader authenticates with a short-lived X-SCORM-Token header, not the
#    session cookie.  Omitting Allow-Credentials means the browser will not attach
#    cookies even if the SCO JS tries to include them.

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,   # :5173 only — never :5174
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# SCORM/cmi5 runtime CORS — content origin allowed, NO credentials
_SCORM_PATHS = ("/api/scorm/", "/api/cmi5/")


@app.middleware("http")
async def scorm_cors_middleware(request: Request, call_next):
    """
    For requests from the content origin hitting SCORM/cmi5 runtime paths, inject
    the minimal CORS headers needed for the loader's XHR — but intentionally
    omit Access-Control-Allow-Credentials so session cookies cannot be used.
    """
    origin = request.headers.get("origin", "")
    is_content_origin = origin == settings.CONTENT_ORIGIN
    is_scorm_path = any(request.url.path.startswith(p) for p in _SCORM_PATHS)

    # Handle preflight
    if request.method == "OPTIONS" and is_content_origin and is_scorm_path:
        return Response(
            status_code=204,
            headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, X-SCORM-Token, Authorization",
                "Access-Control-Max-Age": "600",
                # No Access-Control-Allow-Credentials
            },
        )

    response = await call_next(request)

    if is_content_origin and is_scorm_path:
        response.headers["Access-Control-Allow-Origin"] = origin
        # No Access-Control-Allow-Credentials — intentional
        if "Access-Control-Allow-Credentials" in response.headers:
            del response.headers["Access-Control-Allow-Credentials"]

    return response


# Routers
app.include_router(auth_router)
app.include_router(disciplines_router)
app.include_router(levels_router)
app.include_router(users_router)
app.include_router(courses_router)
app.include_router(sections_router)
app.include_router(content_router)
app.include_router(quiz_router)
app.include_router(questions_router)
app.include_router(options_router)
app.include_router(employee_courses_router)
app.include_router(employee_team_router)
app.include_router(employee_content_router)
app.include_router(scorm_router)
app.include_router(scorm_launch_router)
app.include_router(quiz_engine_router)
app.include_router(cmi5_router)
app.include_router(packages_router)
app.include_router(analytics_router)
app.include_router(admin_sessions_router)
app.include_router(employee_sessions_router)
app.include_router(livekit_webhook_router)


@app.on_event("startup")
def _start_background_jobs():
    from app.services.session_scheduler import start_scheduler as start_session_scheduler
    from app.services.enrollment_scheduler import start_scheduler as start_enrollment_scheduler
    start_session_scheduler()
    start_enrollment_scheduler()


@app.on_event("shutdown")
def _stop_background_jobs():
    from app.services.session_scheduler import shutdown_scheduler as stop_session_scheduler
    from app.services.enrollment_scheduler import shutdown_scheduler as stop_enrollment_scheduler
    stop_session_scheduler()
    stop_enrollment_scheduler()


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "code": "internal_error"},
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/content/download")
def local_content_download(token: str = Query(...), range_header: Optional[str] = Header(None, alias="Range")):
    """
    Serve locally-stored content via a short-lived signed token (LocalBackend only).
    MinIO generates its own presigned URLs (which support Range natively) and
    never routes through here.

    Honors HTTP Range requests (206 Partial Content) — without this, browsers
    can't reliably seek a large <video>: a plain 200 with the whole file forces
    a full re-download on every seek attempt, and playback position restoration
    (resume-from-last-position) silently fails since the browser can't fetch
    just the byte range around the target timestamp.

    Both the ranged and full-file paths stream the response in fixed-size
    chunks (LocalBackend.iter_range) rather than reading the whole file into
    memory first — a 500MB video request never costs more than one chunk of
    server RAM, and the client starts receiving bytes immediately instead of
    waiting for the full read to complete.
    """
    import jwt
    from app.services.storage import LocalBackend, content_type_for

    if settings.STORAGE_BACKEND != "local":
        raise HTTPException(status_code=404, detail="Not found")

    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        key = payload["key"]
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Download URL has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=400, detail="Invalid download token")

    backend = LocalBackend()
    try:
        file_size = backend.file_size(key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Content not found")

    content_type = content_type_for(key)

    if range_header:
        try:
            units, _, range_spec = range_header.partition("=")
            start_str, _, end_str = range_spec.partition("-")
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else file_size - 1
        except ValueError:
            raise HTTPException(status_code=416, detail="Invalid Range header")

        end = min(end, file_size - 1)
        if units != "bytes" or start < 0 or start > end or start >= file_size:
            raise HTTPException(
                status_code=416,
                detail="Range not satisfiable",
                headers={"Content-Range": f"bytes */{file_size}"},
            )

        return StreamingResponse(
            backend.iter_range(key, start, end),
            status_code=206,
            media_type=content_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(end - start + 1),
                "Cache-Control": "no-store",
            },
        )

    return StreamingResponse(
        backend.iter_range(key, 0, file_size - 1),
        media_type=content_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Cache-Control": "no-store",
        },
    )
