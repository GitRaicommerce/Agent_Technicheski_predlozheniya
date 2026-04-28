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

function Wait-ForUrl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [Parameter(Mandatory = $true)]
        [string]$Label
    )

    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                Write-Host "$Label is ready at $Url" -ForegroundColor Green
                return
            }
        } catch {
            Start-Sleep -Seconds $sleepSeconds
        }
    }

    throw "$Label did not become ready in time: $Url"
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
    Write-Host "Starting Docker stack..." -ForegroundColor Cyan
    docker compose -f $composeFile up -d --wait

    Write-Host "Waiting for API..." -ForegroundColor Yellow
    Wait-ForUrl -Url $apiHealthUrl -Label "API"

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
