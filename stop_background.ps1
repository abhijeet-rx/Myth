# stop_background.ps1 - Stop the background Job Watcher process
$PID_FILE = "$PSScriptRoot\.watcher.pid"

Set-Location $PSScriptRoot

if (-not (Test-Path $PID_FILE)) {
    Write-Host "[-] No running Job Watcher PID found." -ForegroundColor Yellow
    exit 0
}

$procId = (Get-Content $PID_FILE).Trim()
if ($procId -match '^\d+$') {
    $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if ($proc) {
        Stop-Process -Id $procId -Force
        Write-Host "[+] Job Watcher process (PID: $procId) has been stopped." -ForegroundColor Green
    } else {
        Write-Host "[-] Process $procId was not running." -ForegroundColor Yellow
    }
}

Remove-Item -Path $PID_FILE -Force -ErrorAction SilentlyContinue
