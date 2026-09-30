$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $repoRoot "docker-compose.dev.yml"
$webUrl = "http://localhost:3000"
$projectsUrl = "http://localhost:3000/projects"
$newProjectUrl = "http://localhost:3000/projects/new"
$warmProjectUrl = "http://localhost:3000/projects/__warmup__"
$apiHealthUrl = "http://localhost:8000/health"
$maxAttempts = 36
$sleepSeconds = 5

function Invoke-Native {
    # $ErrorActionPreference does not stop on a failing external command, so
    # every docker call is checked explicitly (K-19).
    param(
        [Parameter(Mandatory = $true)]
        [string]$Description,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE"
    }
}

function Wait-ForUrl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [Parameter(Mandatory = $true)]
        [string]$Label,
        [switch]$RequireHealthyJson
    )

    $lastProblem = "no response"
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                if (-not $RequireHealthyJson) {
                    Write-Host "$Label is ready at $Url" -ForegroundColor Green
                    return
                }
                $body = $response.Content | ConvertFrom-Json
                if ($body.status -eq "ok") {
                    Write-Host "$Label is ready at $Url (db, redis, migrations ok)" -ForegroundColor Green
                    return
                }
                $lastProblem = "status=$($body.status)"
            }
        } catch {
            # /health answers 503 with the failing dependency while not ready.
            $lastProblem = $_.Exception.Message
            if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
                $lastProblem = $_.ErrorDetails.Message
            }
        }
        Start-Sleep -Seconds $sleepSeconds
    }

    throw "$Label did not become ready in time: $Url ($lastProblem)"
}

function Invoke-WarmUrl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    try {
        Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 15 | Out-Null
        Write-Host "Warmed route: $Url" -ForegroundColor DarkGray
    } catch {
        Write-Warning "Warm-up request failed for $Url"
    }
}

Push-Location $repoRoot
try {
    Write-Host "Starting infrastructure (postgres, redis, minio)..." -ForegroundColor Cyan
    Invoke-Native "Starting infrastructure" { docker compose -f $composeFile up -d --wait postgres redis minio }

    Write-Host "Applying database migrations..." -ForegroundColor Cyan
    Invoke-Native "Database migration (alembic upgrade head)" { docker compose -f $composeFile run --rm api alembic upgrade head }

    Write-Host "Starting application services..." -ForegroundColor Cyan
    Invoke-Native "Starting application services" { docker compose -f $composeFile up -d --wait }

    Write-Host "Waiting for API..." -ForegroundColor Yellow
    Wait-ForUrl -Url $apiHealthUrl -Label "API" -RequireHealthyJson

    Write-Host "Waiting for Web..." -ForegroundColor Yellow
    Wait-ForUrl -Url $webUrl -Label "Web app"

    Write-Host "Warming key routes..." -ForegroundColor Yellow
    Invoke-WarmUrl -Url $projectsUrl
    Invoke-WarmUrl -Url $newProjectUrl
    Invoke-WarmUrl -Url $warmProjectUrl

    Write-Host "Opening app..." -ForegroundColor Cyan
    Start-Process $webUrl
} finally {
    Pop-Location
}
