# start_background.ps1 - Run Myth Job Watcher silently in the background on Windows
$PID_FILE = "$PSScriptRoot\.watcher.pid"
$LOG_FILE = "$PSScriptRoot\watcher.log"

Set-Location $PSScriptRoot

if (Test-Path $PID_FILE) {
    $existingPid = (Get-Content $PID_FILE).Trim()
    if ($existingPid -match '^\d+$') {
        $proc = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "[!] Job Watcher is ALREADY running with PID: $existingPid" -ForegroundColor Yellow
            Write-Host "    Check status:  .\status_watcher.ps1"
            Write-Host "    View live log: Get-Content watcher.log -Tail 20 -Wait"
            Write-Host "    Stop watcher:  .\stop_background.ps1"
            exit 0
        }
    }
    Remove-Item -Path $PID_FILE -Force -ErrorAction SilentlyContinue
}

# Launch python in background detached
$proc = Start-Process -FilePath "python.exe" `
    -ArgumentList "job_watcher.py" `
    -WorkingDirectory $PSScriptRoot `
    -WindowStyle Hidden `
    -PassThru

# Give it 1.5 seconds to initialize and register PID
Start-Sleep -Milliseconds 1500

$runningPid = $proc.Id
if (Test-Path $PID_FILE) {
    $runningPid = (Get-Content $PID_FILE).Trim()
}

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "[+] Myth Job Watcher started successfully!" -ForegroundColor Green
Write-Host "    PID:           $runningPid" -ForegroundColor White
Write-Host "    Cadence:       Every 15 minutes (900 seconds)" -ForegroundColor White
Write-Host "    Target:        4th-Year Fresher (Java/Full-Stack/Backend/Frontend/SDE)" -ForegroundColor White
Write-Host "    Freshness:     Strictly <= 24 hours old" -ForegroundColor White
Write-Host "    Telegram:      Active (Instant alerts on new jobs)" -ForegroundColor White
Write-Host "    Log file:      $LOG_FILE" -ForegroundColor Gray
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "Useful commands:"
Write-Host "  .\status_watcher.ps1                  # Check watcher status & recent scans" -ForegroundColor Yellow
Write-Host "  Get-Content watcher.log -Tail 30 -Wait # Stream live logs in console" -ForegroundColor Yellow
Write-Host "  .\stop_background.ps1                  # Stop the background process" -ForegroundColor Yellow
