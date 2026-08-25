# Restores a bundle produced by scripts\export-for-migration.ps1 onto a
# DIFFERENT VM that's already completed DEPLOYMENT.md steps 1-3 (repo
# checked out, .env.prod filled in with values for THIS VM, and the stack
# already brought up once via scripts\deploy.ps1 so Postgres/MinIO have
# their empty schema/bucket created). This script then overwrites that
# empty state with the real data from the export.
#
# Run this ON THE NEW/TARGET VM, from the repo root:
#   powershell -File scripts\import-migration.ps1 -ExportPath "C:\path\to\lms-migration-20260101-120000"
#
# This is DESTRUCTIVE to whatever is currently in the target VM's Postgres
# database and MinIO bucket — it drops and recreates the database and
# replaces the MinIO volume's contents wholesale. That's correct for a
# "move production to a new VM" scenario (the old VM's data is meant to
# fully replace whatever placeholder/empty state is on the new one) but
# would destroy real data if run against a target that already has its own
# live data — the script refuses to proceed unless you pass -Confirm.

param(
    [Parameter(Mandatory = $true)]
    [string]$ExportPath,
    [switch]$Confirm
)

$ErrorActionPreference = "Stop"
Set-Location -Path (Split-Path -Parent $PSScriptRoot)

$composeFile = "docker-compose.prod.yml"
if (-not (Test-Path $composeFile)) {
    Write-Error "docker-compose.prod.yml not found — run this from the repo root on the target VM."
    exit 1
}
if (-not (Test-Path ".env.prod")) {
    Write-Error ".env.prod not found. Complete DEPLOYMENT.md steps 1-3 on this VM (bootstrap + first deploy) before importing."
    exit 1
}
if (-not (Test-Path $ExportPath)) {
    Write-Error "Export path not found: $ExportPath"
    exit 1
}
$dumpFile = Join-Path $ExportPath "postgres.dump"
$minioArchive = Join-Path $ExportPath "minio_data.tar.gz"
$manifestFile = Join-Path $ExportPath "manifest.json"
foreach ($f in @($dumpFile, $minioArchive, $manifestFile)) {
    if (-not (Test-Path $f)) { Write-Error "Missing expected file in export bundle: $f"; exit 1 }
}
$manifest = Get-Content $manifestFile -Raw | ConvertFrom-Json
Write-Host "Import bundle exported $($manifest.exported_at) from $($manifest.exported_from)"

if (-not $Confirm) {
    Write-Host ""
    Write-Host "THIS WILL PERMANENTLY REPLACE the database and object storage on THIS VM" -ForegroundColor Red
    Write-Host "with the contents of the export bundle. Anything currently in this VM's" -ForegroundColor Red
    Write-Host "Postgres database or MinIO bucket will be destroyed." -ForegroundColor Red
    Write-Host ""
    Write-Host "Re-run with -Confirm to proceed:" -ForegroundColor Yellow
    Write-Host "  powershell -File scripts\import-migration.ps1 -ExportPath `"$ExportPath`" -Confirm"
    exit 1
}

# --env-file required on every docker compose call below — see the matching
# comment in export-for-migration.ps1; without it compose falls back to the
# default .env (dev) file, which points at the wrong POSTGRES_USER/DB or is
# missing vars entirely that only exist in .env.prod.
$composeArgs = @("-f", $composeFile, "--env-file", ".env.prod")

$running = docker compose @composeArgs ps db --format json 2>$null | ConvertFrom-Json
if (-not $running -or $running.State -ne "running") {
    Write-Error "The prod db container isn't running. Run scripts\deploy.ps1 first so the stack (and empty schema) exists."
    exit 1
}

# Read this VM's OWN .env.prod values — deliberately not trusting the
# manifest's recorded user/db name, since this VM's .env.prod is the
# actual source of truth for what the running containers expect.
function Get-EnvValue($name, $default) {
    $line = Get-Content ".env.prod" | Where-Object { $_ -match "^$name=" } | Select-Object -First 1
    if (-not $line) { return $default }
    return ($line -split "=", 2)[1].Trim()
}
$pgUser = Get-EnvValue "POSTGRES_USER" "lms"
$pgDb = Get-EnvValue "POSTGRES_DB" "lms"

# ── 1. Stop api/web so nothing writes to the database mid-restore ───────────
Write-Host "Stopping api/web (db/minio/redis/livekit/caddy stay up)..."
docker compose @composeArgs stop api web
if ($LASTEXITCODE -ne 0) { throw "Failed to stop api/web" }

# ── 2. Restore Postgres ──────────────────────────────────────────────────────
Write-Host "Restoring Postgres database (this replaces all existing data in '$pgDb')..."
$dbContainerId = (docker compose @composeArgs ps -q db).Trim()
docker cp $dumpFile "${dbContainerId}:/tmp/lms_migration.dump"

# Terminate other connections and drop/recreate the target database — a
# straight pg_restore into a non-empty database would fail on every
# already-existing table/constraint instead of cleanly replacing it.
docker compose @composeArgs exec -T db psql -U $pgUser -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$pgDb' AND pid <> pg_backend_pid();"
docker compose @composeArgs exec -T db psql -U $pgUser -d postgres -c "DROP DATABASE IF EXISTS ""$pgDb"";"
docker compose @composeArgs exec -T db psql -U $pgUser -d postgres -c "CREATE DATABASE ""$pgDb"" OWNER $pgUser;"
docker compose @composeArgs exec db pg_restore -U $pgUser -d $pgDb --no-owner /tmp/lms_migration.dump
if ($LASTEXITCODE -ne 0) { throw "pg_restore failed" }
docker compose @composeArgs exec db rm -f /tmp/lms_migration.dump
Write-Host "  Postgres restored."

# ── 3. Restore MinIO volume ──────────────────────────────────────────────────
Write-Host "Restoring MinIO object storage volume (this replaces all existing objects)..."
docker compose @composeArgs stop minio
if ($LASTEXITCODE -ne 0) { throw "Failed to stop minio" }

# `ps -q` alone only lists RUNNING containers — minio was just stopped
# above, so this needs -a (all states) to still find it by container ID
# rather than hardcoding a container name that depends on the compose
# project name never changing.
$minioContainerId = (docker compose @composeArgs ps -a -q minio).Trim()
if (-not $minioContainerId) {
    Write-Error "Could not find the minio container (try 'docker compose -f $composeFile --env-file .env.prod ps -a minio')."
    exit 1
}
# See the matching comment in export-for-migration.ps1: an `{{if eq
# .Destination "..."}}` conditional inside the Go template gets mangled by
# PowerShell's quoting on Windows — emit "dest=name" pairs and filter here
# instead, confirmed to work against a real container.
$mountsRaw = docker inspect $minioContainerId --format "{{range .Mounts}}{{.Destination}}={{.Name}}|{{end}}" 2>$null
$minioVolume = $null
foreach ($pair in ($mountsRaw -split '\|')) {
    if ($pair -match '^/data=(.+)$') { $minioVolume = $Matches[1]; break }
}
if (-not $minioVolume) {
    Write-Error "Could not determine MinIO's volume name from its container mounts."
    exit 1
}
Write-Host "  (volume: $minioVolume)"

$archiveFullPath = (Resolve-Path $minioArchive).Path
$archiveDir = Split-Path $archiveFullPath -Parent
$archiveName = Split-Path $archiveFullPath -Leaf

docker run --rm `
    -v "${minioVolume}:/data" `
    -v "${archiveDir}:/restore" `
    alpine:3.20 `
    sh -c "rm -rf /data/* /data/.[!.]* 2>/dev/null; tar -xzf /restore/$archiveName -C /data"
if ($LASTEXITCODE -ne 0) { throw "MinIO volume restore failed" }

docker compose @composeArgs start minio
if ($LASTEXITCODE -ne 0) { throw "Failed to restart minio" }
Write-Host "  MinIO restored."

# ── 4. Bring api/web back up and run migrations (schema may be newer than the dump) ──
Write-Host "Starting api/web and running migrations..."
docker compose @composeArgs start api web
Start-Sleep -Seconds 5
docker compose @composeArgs exec -T api alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "alembic upgrade head failed after restore" }

Write-Host ""
Write-Host "Import complete." -ForegroundColor Green
Write-Host "Verify: browse to https://<this VM's INTERNAL_HOSTNAME>, log in, confirm" -ForegroundColor Yellow
Write-Host "courses/users/enrollments from the old VM are present, and that an existing" -ForegroundColor Yellow
Write-Host "video/PDF content item still plays (confirms the MinIO restore worked)." -ForegroundColor Yellow
