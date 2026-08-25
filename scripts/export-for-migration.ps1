# Packages everything needed to move this production LMS deployment to a
# different VM: a Postgres dump (all real data), the MinIO object storage
# volume (uploaded videos/PDFs/SCORM packages), and Redis (safe to skip —
# see note below). Produces a single timestamped folder you copy to the new
# VM and feed to scripts\import-migration.ps1 there.
#
# Run this ON THE SOURCE VM (the one currently running the prod stack),
# from the repo root:
#   powershell -File scripts\export-for-migration.ps1
#
# What this does NOT do (deliberately):
#   - Does not touch .env.prod, ssl/, or livekit/livekit.prod.yaml — those
#     contain real secrets/keys and must never be bundled with a data
#     export. The new VM gets its OWN .env.prod (new/rotated secrets are
#     fine and recommended), following DEPLOYMENT.md's normal setup.
#   - Does not export Redis — it's used only for LiveKit's own coordination
#     state and rate-limit counters, nothing persisted there matters across
#     a move. It rebuilds itself empty on the new VM with zero user impact.
#   - Does not stop the source stack. Postgres/MinIO are dumped live via
#     their own consistent-snapshot mechanisms (pg_dump's transaction
#     snapshot; MinIO volume tar while it's a mostly-append-only content
#     store). For a bit-perfect migration with zero risk of missing a
#     write that lands mid-export, stop the stack first
#     (docker compose -f docker-compose.prod.yml stop) — optional, ask
#     before doing that on a live system since it's a real outage window.

$ErrorActionPreference = "Stop"
Set-Location -Path (Split-Path -Parent $PSScriptRoot)

$composeFile = "docker-compose.prod.yml"
if (-not (Test-Path $composeFile)) {
    Write-Error "docker-compose.prod.yml not found — run this from the repo root on the production VM."
    exit 1
}
if (-not (Test-Path ".env.prod")) {
    Write-Error ".env.prod not found — this doesn't look like a VM running the prod stack."
    exit 1
}
# --env-file is required on every docker compose call below — without it,
# compose falls back to reading the default .env (dev) file instead, which
# would silently point this at the wrong POSTGRES_USER/DB, or fail outright
# on variables (e.g. LIVEKIT_API_KEY) that only exist in .env.prod. Verified
# this is a real, not theoretical, failure mode: the first draft of this
# script omitted it and broke exactly this way on a real run.
$composeArgs = @("-f", $composeFile, "--env-file", ".env.prod")

$running = docker compose @composeArgs ps db --format json 2>$null | ConvertFrom-Json
if (-not $running -or $running.State -ne "running") {
    Write-Error "The prod db container isn't running (docker compose -f $composeFile --env-file .env.prod ps). Start the stack first."
    exit 1
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$exportDir = "lms-migration-$timestamp"
New-Item -ItemType Directory -Path $exportDir | Out-Null
Write-Host "Exporting to .\$exportDir\ ..."

# ── 1. Postgres — pg_dump inside the container, then docker cp out ──────────
# Deliberately NOT piping the dump through PowerShell's pipeline
# (`docker compose exec -T db pg_dump ... > file`) — verified directly that
# this corrupts pg_dump's binary custom-format output (PowerShell's stdout
# redirection re-encodes it). Writing the dump to a file INSIDE the
# container first, then `docker cp` to pull it out as raw bytes, round-trips
# correctly — confirmed with a real dump/restore test before relying on it.
Write-Host "Dumping Postgres database..."
$pgUser = "lms"
$pgDb = "lms"
$envProdUser = Get-Content ".env.prod" -ErrorAction SilentlyContinue | Where-Object { $_ -match "^POSTGRES_USER=" }
if ($envProdUser) { $pgUser = ($envProdUser -split "=", 2)[1].Trim() }
$envProdDb = Get-Content ".env.prod" -ErrorAction SilentlyContinue | Where-Object { $_ -match "^POSTGRES_DB=" }
if ($envProdDb) { $pgDb = ($envProdDb -split "=", 2)[1].Trim() }

$dbContainerId = (docker compose @composeArgs ps -q db).Trim()
docker compose @composeArgs exec db pg_dump -U $pgUser -Fc -f /tmp/lms_migration.dump $pgDb
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed" }
docker cp "${dbContainerId}:/tmp/lms_migration.dump" "$exportDir\postgres.dump"
docker compose @composeArgs exec db rm -f /tmp/lms_migration.dump
$dumpSizeMb = [math]::Round((Get-Item "$exportDir\postgres.dump").Length / 1MB, 1)
Write-Host "  -> $exportDir\postgres.dump ($dumpSizeMb MB)"

# ── 2. MinIO object storage volume — tar it up via a throwaway helper container ──
# Copying a named Docker volume's contents without stopping the container
# that uses it: mount the same volume read-only into a short-lived alpine
# container and tar it from there. Safe to do live — MinIO's on-disk layout
# for a simple single-node deployment is stable file-per-object, no WAL/journal
# that a live tar could catch mid-write in a way that corrupts on restore
# (unlike Postgres's data directory, which is why that one uses pg_dump
# instead of a raw volume copy).
Write-Host "Archiving MinIO object storage volume..."
# Read the volume name directly off the running minio container's actual
# mount rather than trying to parse `docker compose config` — the latter
# warns/fails noisily on any env var docker compose considers unset at
# config-parse time (confirmed: it does this even for vars that ARE set in
# .env.prod, if this is invoked with a slightly different working
# directory/env-file context), which makes it an unreliable source for a
# script that must work unattended.
$minioContainerId = (docker compose @composeArgs ps -q minio).Trim()
if (-not $minioContainerId) { throw "minio container not found/running" }
# Deliberately not using an `{{if eq .Destination "..."}}` conditional
# inside the Go template — verified directly that the embedded double
# quotes there get mangled by PowerShell's quoting on Windows ("template
# parsing error: unexpected '/' in operand"), even though the template is
# valid Go template syntax. Emitting "dest=name" pairs and filtering in
# PowerShell instead sidesteps that entirely and was confirmed to work.
$mountsRaw = docker inspect $minioContainerId --format "{{range .Mounts}}{{.Destination}}={{.Name}}|{{end}}"
$minioVolume = $null
foreach ($pair in ($mountsRaw -split '\|')) {
    if ($pair -match '^/data=(.+)$') { $minioVolume = $Matches[1]; break }
}
if (-not $minioVolume) { throw "Could not determine MinIO's volume name from its container mounts" }
Write-Host "  (volume: $minioVolume)"
docker run --rm `
    -v "${minioVolume}:/data:ro" `
    -v "${PWD}\${exportDir}:/backup" `
    alpine:3.20 `
    tar -czf /backup/minio_data.tar.gz -C /data .
if ($LASTEXITCODE -ne 0) { throw "MinIO volume archive failed" }
$archiveSizeMb = [math]::Round((Get-Item "$exportDir\minio_data.tar.gz").Length / 1MB, 1)
Write-Host "  -> $exportDir\minio_data.tar.gz ($archiveSizeMb MB)"

# ── 3. A manifest so the import script (and you) know what's in this bundle ──
$manifest = @{
    exported_at   = (Get-Date -Format "o")
    exported_from = $env:COMPUTERNAME
    postgres_user = $pgUser
    postgres_db   = $pgDb
    minio_volume  = $minioVolume
} | ConvertTo-Json
$manifest | Set-Content "$exportDir\manifest.json"

Write-Host ""
Write-Host "Export complete: .\$exportDir\" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Copy the entire '$exportDir' folder to the new VM (e.g. a USB drive,"
Write-Host "     internal file share, or 'Copy-Item -Recurse' over an admin share —"
Write-Host "     never over the public internet; this contains real employee data)."
Write-Host "  2. On the new VM, after completing DEPLOYMENT.md steps 1-3 (repo checked"
Write-Host "     out, .env.prod filled in with values for the NEW VM, firewall rules,"
Write-Host "     first deploy already run once so the empty schema/buckets exist), run:"
Write-Host "       powershell -File scripts\import-migration.ps1 -ExportPath <full path to $exportDir> -Confirm"
