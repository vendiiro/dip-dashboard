<#
Registers (or removes) the nightly run in Windows Task Scheduler.

  powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1              # Tue-Sat 00:15, local time
  powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1 -Time 00:30
  powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1 -WakeToRun   # also wake the PC from sleep
  powershell -ExecutionPolicy Bypass -File scripts\install_task.ps1 -Remove

Why Tuesday to Saturday at 00:15: US stocks close at 16:00 New York and Europe at about 17:30 CET, so 00:15 in Helsinki is after both,
and a run after midnight Tuesday to Saturday covers the Monday to Friday sessions. The time is the PC's LOCAL time.
The task runs only while you are logged in (it needs your user's Python environment). If the PC was off at the start time,
Windows runs it as soon as possible after the next start (StartWhenAvailable). Not tested on Windows by the author.
#>
param(
    [string]$Time = "00:15",
    [switch]$WakeToRun,
    [switch]$Remove
)
$ErrorActionPreference = "Stop"
$name = "DipDashboard"
$root = Split-Path -Parent $PSScriptRoot
$bat  = Join-Path $root "scripts\run_daily.bat"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false
    Write-Host "Removed task $name"
    return
}
if (-not (Test-Path (Join-Path $root ".venv\Scripts\python.exe"))) {
    throw "No .venv found in $root. Create it first (see START_HERE.md, step 1), then run this again."
}
$action   = New-ScheduledTaskAction -Execute $bat -WorkingDirectory $root
$trigger  = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday,Wednesday,Thursday,Friday,Saturday -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
            -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew
if ($WakeToRun) { $settings.WakeToRun = $true }
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings `
    -Description "Quality-dip screen: refresh dashboard and digest after the market close" -Force | Out-Null
Write-Host "Registered task ${name}: Tue-Sat at $Time (local time), runs $bat"
Write-Host "Test it now:   Start-ScheduledTask -TaskName $name     then read output\run.log"
