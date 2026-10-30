# status_watcher.ps1 - Inspect Myth Job Watcher daemon status and logs
$PID_FILE = "$PSScriptRoot\.watcher.pid"
$LOG_FILE = "$PSScriptRoot\watcher.log"

Set-Location $PSScriptRoot

Write-Host "=== Myth ATS Job Watcher Status ===" -ForegroundColor Cyan

$isRunning = $false
if (Test-Path $PID_FILE) {
    $existingPid = (Get-Content $PID_FILE).Trim()
    if ($existingPid -match '^\d+$') {
        $proc = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($proc) {
            $isRunning = $true
            $memMb = [math]::Round($proc.WorkingSet64 / 1MB, 2)
            $cpuSec = [math]::Round($proc.CPU, 1)
            Write-Host "Status:        RUNNING [ACTIVE]" -ForegroundColor Green
            Write-Host "Process ID:    $existingPid" -ForegroundColor White
            Write-Host "Memory:        $memMb MB" -ForegroundColor White
            Write-Host "CPU Time:      $cpuSec s" -ForegroundColor White
            Write-Host "Cadence:       Every 15 minutes" -ForegroundColor White
        }
    }
}

if (-not $isRunning) {
    Write-Host "Status:        STOPPED" -ForegroundColor Red
    Write-Host "To start:      .\start_background.ps1" -ForegroundColor Yellow
}

Write-Host "`n--- Recent Log Output (Last 15 lines) ---" -ForegroundColor Cyan
if (Test-Path $LOG_FILE) {
    Get-Content $LOG_FILE -Tail 15
} else {
    Write-Host "No log file found yet." -ForegroundColor Gray
}
Write-Host "=========================================" -ForegroundColor Cyan
