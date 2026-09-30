# deploy.ps1 — polls for changes and deploys only when main has new commits.
# Run via Windows Scheduled Task every 1 minute.
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoDir = "C:\Users\Admin\Desktop\Agent_Technicheski_predlozheniya-main"
$HealthUrl = "http://localhost:8000/health"
Set-Location $RepoDir

function Invoke-Native {
    # $ErrorActionPreference does not stop on a failing external command, so
    # every git/docker call is checked explicitly (K-19).
    param(
        [Parameter(Mandatory = $true)]
        [string]$Description,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    $output = & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE"
    }
    return $output
}

function Wait-ForHealthy {
    param([int]$Attempts = 36, [int]$SleepSeconds = 5)

    $lastProblem = "no response"
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 5
            $body = $response.Content | ConvertFrom-Json
            if ($body.status -eq "ok") {
                return
            }
            $lastProblem = "status=$($body.status)"
        } catch {
            $lastProblem = $_.Exception.Message
            if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
                $lastProblem = $_.ErrorDetails.Message
            }
        }
        Start-Sleep -Seconds $SleepSeconds
    }
    throw "API did not become healthy: $lastProblem"
}

# Check if there are new commits on origin/main
Invoke-Native "git fetch" { git fetch origin main } | Out-Null

$LocalHash = Invoke-Native "git rev-parse HEAD" { git rev-parse HEAD }
$RemoteHash = Invoke-Native "git rev-parse origin/main" { git rev-parse origin/main }

if ($LocalHash -eq $RemoteHash) {
    Write-Host "==> No changes detected. Skipping deploy."
    exit 0
}

Write-Host "==> New commits detected. Deploying..."
Invoke-Native "git reset" { git reset --hard origin/main } | Out-Null

Write-Host "==> Building images..."
Invoke-Native "docker compose build" { docker compose build --pull }

Write-Host "==> Running database migrations..."
Invoke-Native "alembic upgrade head" { docker compose run --rm api alembic upgrade head }

Write-Host "==> Restarting containers..."
Invoke-Native "docker compose up" { docker compose up -d --remove-orphans }

Write-Host "==> Waiting for a healthy API (db, redis, migrations)..."
Wait-ForHealthy

Write-Host "==> Removing unused images..."
Invoke-Native "docker image prune" { docker image prune -f } | Out-Null

Write-Host "==> Deploy complete."
docker compose ps
