# publish.ps1 - backup of the database, push to GitHub, health check.
# Started by publish.bat (double-click). Stops at the first problem.
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$backupDir = "C:\Users\Admin\TP_backups"
$healthUrl = "http://localhost:8000/health"

function Stop-WithMessage($text) {
    Write-Host ""
    Write-Host "СПРЯХ: $text" -ForegroundColor Red
    Write-Host "Нищо не е изпратено към GitHub, ако спирането е преди стъпка 2." -ForegroundColor Red
    exit 1
}

Write-Host "=== Стъпка 1 от 3: резервно копие на базата ===" -ForegroundColor Cyan
$containers = @(docker ps --format "{{.Names}}" | Where-Object { $_ -match "postgres" })
if ($LASTEXITCODE -ne 0) { Stop-WithMessage "Docker не отговаря. Стартирай Docker Desktop и опитай пак." }
if ($containers.Count -eq 0) { Stop-WithMessage "Не намерих работеща база (postgres контейнер). Стартирай приложението и опитай пак." }
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$stamp = Get-Date -Format "yyyy-MM-dd_HH-mm"
foreach ($c in $containers) {
    docker exec $c sh -c 'pg_dump -U "$POSTGRES_USER" "${POSTGRES_DB:-$POSTGRES_USER}" > /tmp/tp_backup.sql'
    if ($LASTEXITCODE -ne 0) { Stop-WithMessage "Резервното копие на $c не успя." }
    $file = Join-Path $backupDir "${stamp}_$c.sql"
    docker cp "${c}:/tmp/tp_backup.sql" $file | Out-Null
    if ($LASTEXITCODE -ne 0) { Stop-WithMessage "Не успях да сваля копието от $c." }
    $size = (Get-Item $file).Length
    if ($size -lt 1024) { Stop-WithMessage "Копието $file е подозрително малко ($size байта)." }
    Write-Host ("Копие: {0} ({1:N0} KB)" -f $file, ($size / 1KB)) -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Стъпка 2 от 3: изпращане към GitHub (push) ===" -ForegroundColor Cyan
Set-Location $repo
git push origin main
if ($LASTEXITCODE -ne 0) { Stop-WithMessage "Push не успя (виж съобщението отгоре). Копието на базата е запазено." }
Write-Host "Push е готов." -ForegroundColor Green

Write-Host ""
Write-Host "=== Стъпка 3 от 3: проверка на приложението ===" -ForegroundColor Cyan
Write-Host "Автоматичният deploy обновява приложението и базата. Изчаквам до 10 минути..."
$last = "няма отговор"
for ($i = 1; $i -le 60; $i++) {
    Start-Sleep -Seconds 10
    try {
        $r = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 5
        $b = $r.Content | ConvertFrom-Json
        if ($b.status -eq "ok" -and $b.migrations -eq "ok") {
            Write-Host ""
            Write-Host "ГОТОВО: приложението работи, базата е обновена (миграции ok)." -ForegroundColor Green
            Write-Host "Резервните копия са в $backupDir"
            exit 0
        }
        $last = $r.Content
    } catch {
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) { $last = $_.ErrorDetails.Message } else { $last = $_.Exception.Message }
    }
}
Write-Host ""
Write-Host "ВНИМАНИЕ: за 10 минути приложението не потвърди, че е готово." -ForegroundColor Yellow
Write-Host "Последен отговор: $last" -ForegroundColor Yellow
Write-Host "Копирай този текст и ми го изпрати. Резервните копия са в $backupDir"
exit 1
