# stop_background.ps1 - Stop the background Job Watcher process
$PID_FILE = "$PSScriptRoot\.watcher.pid"

if (-not (Test-Path $PID_FILE)) {
    Write-Host "[-] No running Job Watcher PID found." -ForegroundColor Yellow
    exit
}

$procId = Get-Content $PID_FILE
$proc = Get-Process -Id $procId -ErrorAction SilentlyContinue

if ($proc) {
    Stop-Process -Id $procId -Force
    Write-Host "[+] Job Watcher process ($procId) has been stopped." -ForegroundColor Green
} else {
    Write-Host "[-] Process $procId was not running." -ForegroundColor Yellow
}

Remove-Item -Path $PID_FILE -Force -ErrorAction SilentlyContinue
