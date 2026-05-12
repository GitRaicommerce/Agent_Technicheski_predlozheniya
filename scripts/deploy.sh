#!/usr/bin/env bash
# deploy.sh — runs on the server after a git pull.
# Called by the GitHub Actions deploy workflow.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

echo "==> Pulling latest changes from main..."
git fetch origin main
git reset --hard origin/main

echo "==> Building and restarting containers..."
docker compose pull --ignore-buildable
docker compose build --pull
docker compose up -d --remove-orphans

echo "==> Running database migrations..."
docker compose exec -T api alembic upgrade head

echo "==> Removing unused images..."
docker image prune -f

echo "==> Deploy complete."
docker compose ps
