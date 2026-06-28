# LMS startup script for Windows

Write-Host "Starting infrastructure services..." -ForegroundColor Cyan
docker compose up -d db redis mailpit content

Write-Host "Waiting for database to be ready..." -ForegroundColor Cyan
$attempts = 0
do {
    Start-Sleep -Seconds 2
    $attempts++
    $result = docker compose exec -T db pg_isready -U lms
    $ready = ($LASTEXITCODE -eq 0)
} while (-not $ready -and $attempts -lt 30)

if (-not $ready) {
    Write-Host "Database did not become ready in time." -ForegroundColor Red
    exit 1
}

Write-Host "Running migrations..." -ForegroundColor Cyan
docker compose run --rm api alembic upgrade head
if ($LASTEXITCODE -ne 0) { Write-Host "Migration failed." -ForegroundColor Red; exit 1 }

Write-Host "Seeding database..." -ForegroundColor Cyan
docker compose run --rm api python seed.py

Write-Host ""
Write-Host "Starting API and web servers..." -ForegroundColor Cyan
Write-Host "LMS will be available at:" -ForegroundColor Green
Write-Host "  Web:     http://localhost:5173" -ForegroundColor Green
Write-Host "  API:     http://localhost:8000/docs" -ForegroundColor Green
Write-Host "  Mailpit: http://localhost:8025" -ForegroundColor Green
Write-Host ""
Write-Host "Admin: admin@lms.internal / Admin123!" -ForegroundColor Green
Write-Host ""
docker compose up api web
