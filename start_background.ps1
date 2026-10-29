# start_background.ps1 - Run Myth Job Watcher silently in the background on Windows
$PID_FILE = "$PSScriptRoot\.watcher.pid"

if (Test-Path $PID_FILE) {
    $existingPid = Get-Content $PID_FILE
    $proc = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "[!] Job Watcher is ALREADY running with PID: $existingPid" -ForegroundColor Yellow
        exit
    }
}

$proc = Start-Process -FilePath "py.exe" -ArgumentList "job_watcher.py" -WindowStyle Hidden -PassThru
$proc.Id | Out-File -FilePath $PID_FILE -Encoding utf8

Write-Host "[+] Myth Job Watcher started in background!" -ForegroundColor Green
Write-Host "    PID: $($proc.Id)"
Write-Host "    Poll Interval: Every 30 minutes"
Write-Host "    Telegram alerts: Enabled"
Write-Host "    To stop it anytime, run: .\stop_background.ps1"
