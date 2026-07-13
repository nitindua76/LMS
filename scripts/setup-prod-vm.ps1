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
$rules = @(
    @{ Name = "LMS HTTPS";           Port = 443;              Protocol = "TCP" }
    @{ Name = "LMS LiveKit WSS";     Port = 7880;             Protocol = "TCP" }
    @{ Name = "LMS LiveKit RTC TCP"; Port = 7881;             Protocol = "TCP" }
    @{ Name = "LMS Content Origin";  Port = 5174;             Protocol = "TCP" }
)
foreach ($r in $rules) {
    if (-not (Get-NetFirewallRule -DisplayName $r.Name -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $r.Name -Direction Inbound -Protocol $r.Protocol `
            -LocalPort $r.Port -Action Allow | Out-Null
        Write-Host "Added firewall rule: $($r.Name)"
    }
}
# RTC media UDP range — read from .env.prod if it exists yet, else default
$rtcStart = 55000; $rtcEnd = 55100
if (Test-Path ".env.prod") {
    $line = Get-Content ".env.prod" | Where-Object { $_ -match "^LIVEKIT_RTC_PORT_RANGE_START=" }
    if ($line) { $rtcStart = ($line -split "=", 2)[1].Trim() }
    $line = Get-Content ".env.prod" | Where-Object { $_ -match "^LIVEKIT_RTC_PORT_RANGE_END=" }
    if ($line) { $rtcEnd = ($line -split "=", 2)[1].Trim() }
}
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
