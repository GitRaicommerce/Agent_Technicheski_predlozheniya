# deploy.ps1 — polls for changes and deploys only when main has new commits.
# Run via Windows Scheduled Task every 1 minute.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoDir = "C:\Users\Admin\Desktop\Agent_Technicheski_predlozheniya-main"
Set-Location $RepoDir

# Check if there are new commits on origin/main
git fetch origin main

$LocalHash = git rev-parse HEAD
$RemoteHash = git rev-parse origin/main

if ($LocalHash -eq $RemoteHash) {
    Write-Host "==> No changes detected. Skipping deploy."
    exit 0
}

Write-Host "==> New commits detected. Deploying..."
git reset --hard origin/main

Write-Host "==> Building and restarting containers..."
docker compose build --pull
docker compose up -d --remove-orphans

Write-Host "==> Running database migrations..."
docker compose exec -T api alembic upgrade head

Write-Host "==> Removing unused images..."
docker image prune -f

Write-Host "==> Deploy complete."
docker compose ps
