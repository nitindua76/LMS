# ─────────────────────────────────────────────────────────────────────────────
# LMS startup script for the OFFICE machine (appserver1.ongc.co.in)
#
# Differs from start.ps1 (plain localhost dev) in that the office machine:
#   - Serves everything over HTTPS via the nginx TLS proxy (needed for
#     camera/mic in live sessions — browsers require a secure context)
#   - Uses the ONGC hostname + internal DNS + corporate proxy settings,
#     all of which live in the office machine's OWN .env (gitignored, so it
#     never gets overwritten by a `git pull` from the dev laptop)
#
# This script is safe to re-run any time — it pulls latest code, applies any
# new DB migrations, and (re)starts the whole stack behind nginx.
#
# Usage:  .\start-office.ps1            (pull + migrate + start everything)
#         .\start-office.ps1 -NoPull    (skip git pull — start what's on disk)
#         .\start-office.ps1 -Build     (rebuild api/web images — after a
#                                        requirements.txt / package.json change)
#         .\start-office.ps1 -Seed      (also seed admin user + reference data —
#                                        only needed on a fresh/empty database)
# ─────────────────────────────────────────────────────────────────────────────
param(
    [switch]$NoPull,
    [switch]$Build,
    [switch]$Seed
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Write-Step($msg)  { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "    $msg"   -ForegroundColor Green }
function Write-WarnLine($msg) { Write-Host "    $msg" -ForegroundColor Yellow }
function Fail($msg)        { Write-Host "`nERROR: $msg" -ForegroundColor Red; exit 1 }

# ── 0. Pre-flight: required files must exist ─────────────────────────────────
Write-Step "Checking required files for the office (TLS) setup"

if (-not (Test-Path ".env")) {
    Fail ".env is missing. Copy .env.example to .env and fill in the office values (ONGC hostname, DNS, proxy, SSO/Employee API keys). This file is gitignored and must live only on this machine."
}
Write-Ok ".env found"

if (-not (Test-Path "nginx/nginx.conf")) {
    Fail "nginx/nginx.conf is missing. It's tracked in git now, so a git pull should restore it. Run: git checkout -- nginx/nginx.conf"
}
Write-Ok "nginx/nginx.conf found"

# TLS certs are gitignored (machine-local) — verify the two files the nginx
# config references actually exist before we try to start nginx, since a
# missing cert is exactly what produces nginx's "internal server error".
$certPath = "ssl/ONGC2526.crt"
$keyPath  = "ssl/ONGC2526KEY.decrypted.key"
if (-not (Test-Path $certPath)) {
    Fail "TLS certificate missing: ${certPath}. ssl/ is gitignored, so the cert files must be placed here manually on this machine."
}
if (-not (Test-Path $keyPath)) {
    Fail "TLS private key missing: ${keyPath}. ssl/ is gitignored, so the key files must be placed here manually on this machine."
}
Write-Ok "TLS certificate + key found in ssl/"

# ── 0b. Warn if the office .env still has dev/localhost values ───────────────
$envText = Get-Content ".env" -Raw
if ($envText -match "VITE_ALLOWED_HOSTS\s*=\s*localhost") {
    Write-WarnLine "VITE_ALLOWED_HOSTS is set to 'localhost' — the office browser hits appserver1.ongc.co.in and Vite will BLOCK it. Set VITE_ALLOWED_HOSTS=appserver1.ongc.co.in in .env."
}
if ($envText -notmatch "appserver1\.ongc\.co\.in") {
    Write-WarnLine ".env has no reference to appserver1.ongc.co.in — this looks like a dev/localhost .env, not the office one. Double-check CORS_ORIGINS / LIVEKIT_HOST / VITE_ALLOWED_HOSTS."
}

# ── 1. Pull latest code (unless -NoPull) ─────────────────────────────────────
if (-not $NoPull) {
    Write-Step "Pulling latest code from git"
    git pull
    if ($LASTEXITCODE -ne 0) { Fail "git pull failed. Resolve conflicts, then re-run (or use -NoPull to skip)." }
    Write-Ok "Up to date"
} else {
    Write-WarnLine "Skipping git pull (-NoPull)"
}

# ── 2. Optionally rebuild images (after a dependency change) ─────────────────
if ($Build) {
    Write-Step "Rebuilding api + web images (dependencies changed)"
    docker compose build api web
    if ($LASTEXITCODE -ne 0) { Fail "docker compose build failed." }
    Write-Ok "Images rebuilt"
}

# ── 3. Start infrastructure services ─────────────────────────────────────────
Write-Step "Starting infrastructure (db, redis, minio, mailpit, content, livekit, lrs)"
docker compose up -d db redis minio mailpit content livekit lrs
if ($LASTEXITCODE -ne 0) { Fail "Failed to start infrastructure services." }

# ── 4. Wait for the database ─────────────────────────────────────────────────
Write-Step "Waiting for the database to accept connections"
$attempts = 0
do {
    Start-Sleep -Seconds 2
    $attempts++
    docker compose exec -T db pg_isready -U lms | Out-Null
    $ready = ($LASTEXITCODE -eq 0)
} while (-not $ready -and $attempts -lt 30)
if (-not $ready) { Fail "Database did not become ready in time." }
Write-Ok "Database is ready"

# ── 5. Apply migrations ──────────────────────────────────────────────────────
Write-Step "Applying database migrations (alembic upgrade head)"
docker compose run --rm -T api alembic upgrade head
if ($LASTEXITCODE -ne 0) { Fail "Migration failed. The stack was NOT fully started." }
Write-Ok "Schema is up to date"

# ── 5b. Optionally seed (idempotent — only meaningful on a fresh DB) ─────────
if ($Seed) {
    Write-Step "Seeding admin user + reference data (idempotent)"
    docker compose run --rm -T api python seed.py
    if ($LASTEXITCODE -ne 0) { Fail "Seeding failed." }
    Write-Ok "Seed complete"
}

# ── 6. Start api + web (detached), then the nginx TLS proxy ──────────────────
# nginx must come up AFTER api/web exist so its upstreams resolve on the
# compose network. The 'tls' profile is what the dev laptop's
# docker-compose.override.yml disables — but on the office machine we WANT
# nginx, so we start it explicitly by name (which ignores profile gating).
Write-Step "Starting api + web"
docker compose up -d api web
if ($LASTEXITCODE -ne 0) { Fail "Failed to start api/web." }
Write-Ok "api + web running"

Write-Step "Starting nginx TLS proxy"
docker compose up -d nginx
if ($LASTEXITCODE -ne 0) { Fail "Failed to start nginx. Check TLS certs in ssl/ and nginx/nginx.conf." }
Write-Ok "nginx running"

# ── 7. Done — print the office URLs ──────────────────────────────────────────
Write-Host ""
Write-Host "LMS (office) is running behind HTTPS:" -ForegroundColor Green
Write-Host "  Web:     https://appserver1.ongc.co.in:5173" -ForegroundColor Green
Write-Host "  API:     https://appserver1.ongc.co.in:8000/docs" -ForegroundColor Green
Write-Host "  Content: https://appserver1.ongc.co.in:5175" -ForegroundColor Green
Write-Host "  LiveKit: wss://appserver1.ongc.co.in:7880 (signaling)" -ForegroundColor Green
Write-Host ""
Write-Host "Follow logs with:  docker compose logs -f api web nginx" -ForegroundColor DarkGray
Write-Host "Stop everything:   docker compose down" -ForegroundColor DarkGray
Write-Host ""
