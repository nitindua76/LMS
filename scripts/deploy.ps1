# Deploys/updates the production stack on this VM. Run manually for the
# first-ever deploy; after that, the self-hosted GitHub Actions runner on
# this same VM calls this script automatically after every push to main
# (see .github/workflows/deploy.yml).
#
# Usage: powershell -File scripts\deploy.ps1
# Assumes: Docker Desktop running, repo checked out at a fixed path with
# .env.prod already filled in (see .env.prod.example), and (for the very
# first run) already logged into ghcr.io if the GHCR images are private
# (`docker login ghcr.io -u <user> -p <PAT>`) — not needed if the packages
# are set to public in GitHub's package settings.

$ErrorActionPreference = "Stop"
Set-Location -Path (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path ".env.prod")) {
    Write-Error ".env.prod not found. Copy .env.prod.example to .env.prod and fill in real values first."
    exit 1
}

function Get-EnvValue($name) {
    $line = Get-Content ".env.prod" | Where-Object { $_ -match "^$name=" } | Select-Object -First 1
    if (-not $line) { return $null }
    return ($line -split "=", 2)[1].Trim()
}

# ── Render the LiveKit config from the template + .env.prod ─────────────────
Write-Host "Rendering livekit/livekit.prod.yaml from template..."
$nodeIp = Get-EnvValue "LIVEKIT_NODE_IP"
$rtcStart = Get-EnvValue "LIVEKIT_RTC_PORT_RANGE_START"
$rtcEnd = Get-EnvValue "LIVEKIT_RTC_PORT_RANGE_END"
# Defaults to 8781 (not LiveKit's usual 7881) — this machine also runs
# docker-compose.yml (dev) concurrently, which already publishes 7881
# directly; see DEPLOYMENT.md's "Running dev and prod concurrently".
$rtcTcpPort = Get-EnvValue "PROD_LIVEKIT_RTC_TCP_PORT"
if (-not $rtcTcpPort) { $rtcTcpPort = "8781" }
$lkKey = Get-EnvValue "LIVEKIT_API_KEY"
$lkSecret = Get-EnvValue "LIVEKIT_API_SECRET"

if (-not $nodeIp -or -not $lkKey -or -not $lkSecret) {
    Write-Error "LIVEKIT_NODE_IP / LIVEKIT_API_KEY / LIVEKIT_API_SECRET must be set in .env.prod"
    exit 1
}

(Get-Content "livekit/livekit.prod.yaml.template") `
    -replace "__NODE_IP__", $nodeIp `
    -replace "__RTC_PORT_RANGE_START__", $rtcStart `
    -replace "__RTC_PORT_RANGE_END__", $rtcEnd `
    -replace "__RTC_TCP_PORT__", $rtcTcpPort `
    -replace "__LIVEKIT_KEY__", $lkKey `
    -replace "__LIVEKIT_SECRET__", $lkSecret `
    | Set-Content "livekit/livekit.prod.yaml"

# ── Pull the latest images and (re)start ─────────────────────────────────────
Write-Host "Pulling latest images..."
docker compose -f docker-compose.prod.yml --env-file .env.prod pull
if ($LASTEXITCODE -ne 0) { throw "docker compose pull failed" }

Write-Host "Starting/updating the stack..."
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }

# ── Wait for the api container to be healthy, then run migrations ───────────
# --env-file on every call below — without it, `docker compose ps`/`exec`
# still happen to work here (Compose can infer the already-running
# project from its own local state cache), but they print a noisy
# "variable not set" warning to stderr for every var only defined in
# .env.prod, and it's not something to rely on staying true across
# Compose versions. Confirmed via a real deploy run that hit this exact
# warning before being fixed here.
Write-Host "Waiting for api to be ready..."
$maxAttempts = 30
for ($i = 0; $i -lt $maxAttempts; $i++) {
    $status = docker compose -f docker-compose.prod.yml --env-file .env.prod ps api --format json 2>$null | ConvertFrom-Json
    if ($status -and $status.State -eq "running") { break }
    Start-Sleep -Seconds 2
}

Write-Host "Running database migrations..."
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T api alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "alembic upgrade head failed" }

# ── Clean up old, now-unused image layers so disk doesn't grow unbounded ────
Write-Host "Pruning old images..."
docker image prune -f

Write-Host "Deploy complete."
