# One-time production VM bootstrap. Run this once, manually, as
# Administrator, after checking out the repo on the VM and before the
# first-ever deploy. Everything after this is automatic (CI/CD calls
# scripts/deploy.ps1 on every push to main).
#
# Usage (as Administrator): powershell -File scripts\setup-prod-vm.ps1

$ErrorActionPreference = "Stop"
Set-Location -Path (Split-Path -Parent $PSScriptRoot)

# ── 1. Docker Desktop check ───────────────────────────────────────────────────
# Not auto-installed here on purpose: Docker Desktop's unattended install
# needs WSL2 enabled first, which typically needs its own reboot before
# Docker itself can be installed — scripting that blind is more likely to
# leave the VM half-configured than to save real time. Install it yourself
# once (https://www.docker.com/products/docker-desktop/), then re-run this.
$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    Write-Error "Docker not found. Install Docker Desktop (with WSL2 backend), reboot if prompted, then re-run this script."
    exit 1
}
try { docker info | Out-Null } catch {
    Write-Error "Docker is installed but not running/responding. Start Docker Desktop and re-run."
    exit 1
}
Write-Host "Docker OK."

# ── 2. Firewall rules for the ports this stack actually needs inbound ───────
#
# Ports default to the values docker-compose.prod.yml/Caddyfile themselves
# default to (8543/8780/8781/8174/9002), NOT LiveKit's/HTTPS's usual
# 443/7880/7881/5174 — this machine also runs docker-compose.yml (dev)
# concurrently, which already occupies 7880/7881/5174, and separately,
# port 443 falls inside this host's own Windows-reserved TCP port
# exclusion range and cannot be bound at all here regardless of dev. If
# .env.prod overrides any PROD_* port, read that instead of hardcoding.
# See DEPLOYMENT.md's "Running dev and prod concurrently" section.
function Get-EnvValueOrDefault($name, $default) {
    if (-not (Test-Path ".env.prod")) { return $default }
    $line = Get-Content ".env.prod" | Where-Object { $_ -match "^$name=" } | Select-Object -First 1
    if (-not $line) { return $default }
    return ($line -split "=", 2)[1].Trim()
}
$httpsPort = Get-EnvValueOrDefault "PROD_HTTPS_PORT" "8543"
$livekitWssPort = Get-EnvValueOrDefault "PROD_LIVEKIT_WSS_PORT" "8780"
$livekitRtcTcpPort = Get-EnvValueOrDefault "PROD_LIVEKIT_RTC_TCP_PORT" "8781"
$contentPort = Get-EnvValueOrDefault "PROD_CONTENT_PORT" "8174"
$minioPublicPort = Get-EnvValueOrDefault "PROD_MINIO_PUBLIC_PORT" "9002"

$rules = @(
    @{ Name = "LMS HTTPS";           Port = $httpsPort;         Protocol = "TCP" }
    @{ Name = "LMS LiveKit WSS";     Port = $livekitWssPort;    Protocol = "TCP" }
    @{ Name = "LMS LiveKit RTC TCP"; Port = $livekitRtcTcpPort; Protocol = "TCP" }
    @{ Name = "LMS Content Origin";  Port = $contentPort;       Protocol = "TCP" }
    @{ Name = "LMS MinIO Public";    Port = $minioPublicPort;   Protocol = "TCP" }
)
foreach ($r in $rules) {
    if (-not (Get-NetFirewallRule -DisplayName $r.Name -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $r.Name -Direction Inbound -Protocol $r.Protocol `
            -LocalPort $r.Port -Action Allow | Out-Null
        Write-Host "Added firewall rule: $($r.Name) ($($r.Port))"
    }
}
# RTC media UDP range — read from .env.prod if it exists yet, else default
# to 56000-56100 (not LiveKit's usual 55000-55100 — dev already owns that
# range on this host when running concurrently).
$rtcStart = Get-EnvValueOrDefault "LIVEKIT_RTC_PORT_RANGE_START" "56000"
$rtcEnd = Get-EnvValueOrDefault "LIVEKIT_RTC_PORT_RANGE_END" "56100"
$udpRuleName = "LMS LiveKit RTC UDP"
if (-not (Get-NetFirewallRule -DisplayName $udpRuleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $udpRuleName -Direction Inbound -Protocol UDP `
        -LocalPort "$rtcStart-$rtcEnd" -Action Allow | Out-Null
    Write-Host "Added firewall rule: $udpRuleName ($rtcStart-$rtcEnd)"
}

# ── 3. .env.prod ─────────────────────────────────────────────────────────────
if (-not (Test-Path ".env.prod")) {
    Copy-Item ".env.prod.example" ".env.prod"
    Write-Host ""
    Write-Host "Created .env.prod from the template — EDIT IT NOW with real secrets" -ForegroundColor Yellow
    Write-Host "and this VM's actual internal IP (LIVEKIT_NODE_IP) before continuing." -ForegroundColor Yellow
    Write-Host "Re-run this script after editing .env.prod to continue with the first deploy."
    exit 0
}

# ── 4. First deploy ───────────────────────────────────────────────────────────
Write-Host "Running first deploy..."
& "$PSScriptRoot\deploy.ps1"

Write-Host ""
Write-Host "Bootstrap complete. Next: install a self-hosted GitHub Actions runner on" -ForegroundColor Green
Write-Host "this VM (repo Settings -> Actions -> Runners -> New self-hosted runner)" -ForegroundColor Green
Write-Host "so future pushes to main deploy automatically. See DEPLOYMENT.md." -ForegroundColor Green
