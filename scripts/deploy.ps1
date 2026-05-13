# deploy.ps1 — runs on the Windows server after a git pull.
# Called by the GitHub Actions deploy workflow via SSH.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoDir = "C:\Users\Admin\Desktop\Agent_Technicheski_predlozheniya-main"
Set-Location $RepoDir

Write-Host "==> Pulling latest changes from main..."
git fetch origin main
git reset --hard origin/main

Write-Host "==> Building and restarting containers..."
docker compose pull --ignore-buildable
docker compose build --pull
docker compose up -d --remove-orphans

Write-Host "==> Running database migrations..."
docker compose exec -T api alembic upgrade head

Write-Host "==> Removing unused images..."
docker image prune -f

Write-Host "==> Deploy complete."
docker compose ps
