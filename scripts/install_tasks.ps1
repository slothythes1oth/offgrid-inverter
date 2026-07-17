# Deployment hardening (phase 3, item 4): register the collector and the web
# app as Windows Scheduled Tasks that start at boot (no login needed), restart
# on failure, and never get killed by the 72h execution limit.
#
# Run ONCE from an elevated PowerShell:
#   powershell -ExecutionPolicy Bypass -File scripts\install_tasks.ps1
# Remove both tasks:
#   powershell -ExecutionPolicy Bypass -File scripts\install_tasks.ps1 -Remove
#
# Both processes log to files (data\collector.log rotates itself), so running
# headless as SYSTEM loses nothing. Stop/start manually any time with:
#   Stop-ScheduledTask -TaskName "Solarmon Collector"   (or "Solarmon Web")
#   Start-ScheduledTask -TaskName "Solarmon Collector"

param([switch]$Remove)

$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "This script must run in an ELEVATED PowerShell (Run as administrator)." -ForegroundColor Red
    exit 1
}

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "venv python not found at $py" -ForegroundColor Red
    exit 1
}

$tasks = @(
    @{ Name = "Solarmon Collector"; Args = "-m solarmon.main" },
    @{ Name = "Solarmon Web";       Args = "-m solarapi" }
)

foreach ($t in $tasks) {
    $existing = Get-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue
    if ($existing) {
        Stop-ScheduledTask -TaskName $t.Name -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $t.Name -Confirm:$false
        Write-Host "removed existing task: $($t.Name)"
    }
    if ($Remove) { continue }

    $action = New-ScheduledTaskAction -Execute $py -Argument $t.Args -WorkingDirectory $root
    $trigger = New-ScheduledTaskTrigger -AtStartup
    # SYSTEM: starts at boot with no login and no stored password.
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $t.Name -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings | Out-Null
    Start-ScheduledTask -TaskName $t.Name
    Write-Host "installed + started: $($t.Name)" -ForegroundColor Green
}

if ($Remove) {
    Write-Host "done: tasks removed."
} else {
    Write-Host ""
    Write-Host "Both tasks run at every boot, restart on failure (10x, 1 min apart)."
    Write-Host "IMPORTANT: never ALSO start the collector manually while the task runs"
    Write-Host "(the stick tolerates one connection). Check status with:"
    Write-Host '  Get-ScheduledTask -TaskName "Solarmon*" | Get-ScheduledTaskInfo'
}
