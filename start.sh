#!/usr/bin/env bash
set -e

# Copy .env.example to .env if it doesn't exist
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example — edit JWT_SECRET before production use."
fi

echo "Starting services..."
docker compose up -d db redis mailpit content

echo "Waiting for database to be ready..."
until docker compose exec -T db pg_isready -U lms > /dev/null 2>&1; do
  sleep 1
done

echo "Running migrations..."
docker compose run --rm api alembic upgrade head

echo "Seeding database..."
docker compose run --rm api python seed.py

echo "Starting API and web..."
docker compose up api web

echo "
LMS is running:
  Web:     http://localhost:5173
  API:     http://localhost:8000/docs
  Mailpit: http://localhost:8025

Admin credentials:
  Email:    admin@lms.internal
  Password: Admin123!
"
