#!/usr/bin/env bash
# deploy.sh — runs on the server after a git pull.
# Called by the GitHub Actions deploy workflow.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HEALTH_URL="${HEALTH_URL:-http://localhost:8000/health}"
cd "$REPO_DIR"

echo "==> Pulling latest changes from main..."
git fetch origin main
git reset --hard origin/main

echo "==> Building images..."
docker compose pull --ignore-buildable
docker compose build --pull

# K-19: migrate before the new code serves traffic; a failure stops here.
echo "==> Running database migrations..."
docker compose run --rm api alembic upgrade head

echo "==> Restarting containers..."
docker compose up -d --remove-orphans

echo "==> Waiting for a healthy API (db, redis, migrations)..."
healthy=0
for _ in $(seq 1 36); do
  # /health answers 503 until every dependency and the schema are ready.
  if curl -fsS "$HEALTH_URL" | grep -q '"status":"ok"'; then
    healthy=1
    break
  fi
  sleep 5
done
if [ "$healthy" -ne 1 ]; then
  echo "!! API did not become healthy: $(curl -sS "$HEALTH_URL" || true)" >&2
  exit 1
fi

echo "==> Removing unused images..."
docker image prune -f

echo "==> Deploy complete."
docker compose ps
