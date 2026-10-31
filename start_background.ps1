# start_background.ps1 - Run Myth Job Watcher silently in the background on Windows
$PID_FILE = "$PSScriptRoot\.watcher.pid"
$LOCK_FILE = "$PSScriptRoot\.watcher.lock"
$LOG_FILE = "$PSScriptRoot\watcher.log"

Set-Location $PSScriptRoot

# Check if any job_watcher.py process is already running
$runningProcesses = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*job_watcher.py*" }
if ($runningProcesses) {
    $pids = ($runningProcesses | ForEach-Object { $_.ProcessId }) -join ", "
    Write-Host "[!] Job Watcher is ALREADY running with PID(s): $pids" -ForegroundColor Yellow
    Write-Host "    Check status:  .\status_watcher.ps1"
    Write-Host "    View live log: Get-Content watcher.log -Tail 20 -Wait"
    Write-Host "    Stop watcher:  .\stop_background.ps1"
    exit 0
}

# Clean stale PID or lock files if no processes are running
if (Test-Path $PID_FILE) { Remove-Item -Path $PID_FILE -Force -ErrorAction SilentlyContinue }
if (Test-Path $LOCK_FILE) { Remove-Item -Path $LOCK_FILE -Force -ErrorAction SilentlyContinue }

# Launch python in background detached
$proc = Start-Process -FilePath "python.exe" `
    -ArgumentList "job_watcher.py" `
    -WorkingDirectory $PSScriptRoot `
    -WindowStyle Hidden `
    -PassThru

# Give it 2 seconds to initialize, acquire exclusive lock, and write PID
Start-Sleep -Milliseconds 2000

$runningPid = $proc.Id
if (Test-Path $PID_FILE) {
    $runningPid = (Get-Content $PID_FILE).Trim()
}

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "[+] Myth Job Watcher started successfully!" -ForegroundColor Green
Write-Host "    PID:           $runningPid" -ForegroundColor White
Write-Host "    Cadence:       Every 1 hour (3600 seconds)" -ForegroundColor White
Write-Host "    Candidate:     Abhijeet Singh (B.Tech CSE Core, 2023-2027)" -ForegroundColor White
Write-Host "    Target Roles:  SDE, SWE, Java Developer, Backend (Spring Boot), Full-Stack, MTS, Intern" -ForegroundColor White
Write-Host "    Deduplication: Multi-layer (ID + URL + Semantic Fingerprint + OS Lock)" -ForegroundColor White
Write-Host "    Freshness:     Strictly <= 24 hours old (Jobs & Internships)" -ForegroundColor White
Write-Host "    Telegram:      Active (Instant alerts on new jobs)" -ForegroundColor White
Write-Host "    Log file:      $LOG_FILE" -ForegroundColor Gray
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "Useful commands:"
Write-Host "  .\status_watcher.ps1                  # Check watcher status & recent scans" -ForegroundColor Yellow
Write-Host "  Get-Content watcher.log -Tail 30 -Wait # Stream live logs in console" -ForegroundColor Yellow
Write-Host "  .\stop_background.ps1                  # Stop the background process" -ForegroundColor Yellow
