# status_watcher.ps1 - Inspect Myth Job Watcher daemon status and logs
$PID_FILE = "$PSScriptRoot\.watcher.pid"
$LOCK_FILE = "$PSScriptRoot\.watcher.lock"
$LOG_FILE = "$PSScriptRoot\watcher.log"

Set-Location $PSScriptRoot

Write-Host "=== Myth ATS Job Watcher Status ===" -ForegroundColor Cyan

$runningProcesses = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*job_watcher.py*" }

if ($runningProcesses) {
    $count = ($runningProcesses | Measure-Object).Count
    if ($count -gt 1) {
        Write-Host "Status:        WARNING [MULTIPLE PROCESSES DETECTED: $count]" -ForegroundColor Yellow
        Write-Host "               Run .\stop_background.ps1 to cleanly reset." -ForegroundColor Yellow
    } else {
        Write-Host "Status:        RUNNING [HEALTHY - 1 PROCESS]" -ForegroundColor Green
    }

    foreach ($procCim in $runningProcesses) {
        $p = Get-Process -Id $procCim.ProcessId -ErrorAction SilentlyContinue
        if ($p) {
            $memMb = [math]::Round($p.WorkingSet64 / 1MB, 2)
            $cpuSec = [math]::Round($p.CPU, 1)
            Write-Host "Process ID:    $($p.Id) (Memory: $memMb MB, CPU: $cpuSec s)" -ForegroundColor White
        }
    }

    Write-Host "Candidate:     Abhijeet Singh (B.Tech CSE Core, 2023-2027)" -ForegroundColor White
    Write-Host "Target Roles:  SDE, SWE, Java Developer, Backend (Spring Boot), Full-Stack, MTS, Intern" -ForegroundColor White
    Write-Host "Cadence:       Every 1 hour" -ForegroundColor White
} else {
    Write-Host "Status:        STOPPED" -ForegroundColor Red
    Write-Host "To start:      .\start_background.ps1" -ForegroundColor Yellow
}

Write-Host "`n--- Recent Log Output (Last 20 lines) ---" -ForegroundColor Cyan
if (Test-Path $LOG_FILE) {
    Get-Content $LOG_FILE -Tail 20
} else {
    Write-Host "No log file found yet." -ForegroundColor Gray
}
Write-Host "=========================================" -ForegroundColor Cyan
