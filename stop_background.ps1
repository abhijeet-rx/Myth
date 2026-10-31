# stop_background.ps1 - Stop any running Job Watcher daemon processes
$PID_FILE = "$PSScriptRoot\.watcher.pid"
$LOCK_FILE = "$PSScriptRoot\.watcher.lock"

Set-Location $PSScriptRoot

$runningProcesses = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*job_watcher.py*" }

if ($runningProcesses) {
    foreach ($p in $runningProcesses) {
        try {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
            Write-Host "[+] Stopped Job Watcher process (PID: $($p.ProcessId))" -ForegroundColor Green
        } catch {
            Write-Host "[-] Failed to stop PID $($p.ProcessId): $_" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "[-] No running Job Watcher process found." -ForegroundColor Yellow
}

# Clean tracking files
Remove-Item -Path $PID_FILE -Force -ErrorAction SilentlyContinue
Remove-Item -Path $LOCK_FILE -Force -ErrorAction SilentlyContinue
