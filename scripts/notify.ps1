<#
 Desktop notification for the daily screen. Reads output\alerts_latest.json and shows ONE balloon notification:
 the number of research conditions met plus the top 3 headlines. Informational only, not investment advice.
 No modules are installed; it uses System.Windows.Forms, which ships with Windows PowerShell.
 Nothing is sent over the network.

 Usage:
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\notify.ps1 -DryRun     (prints, shows nothing)
   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\notify.ps1              (shows the balloon)
   -Path <file>   read another alerts file (default: output\alerts_latest.json next to this script's parent folder)
#>
param(
    [string]$Path = (Join-Path (Split-Path -Parent $PSScriptRoot) "output\alerts_latest.json"),
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$top = 3

if (-not (Test-Path -LiteralPath $Path)) { Write-Output "No alerts file at $Path; nothing to show."; exit 0 }
try {
    $data = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Write-Output "Alerts file could not be read ($($_.Exception.Message)); nothing to show."; exit 0
}
$alerts = @($data.alerts)
$n = $alerts.Count
if ($n -eq 0) { Write-Output "No conditions met for data date $($data.asof); no notification."; exit 0 }

$noun = if ($n -eq 1) { "condition" } else { "conditions" }
$title = "Dip screen: $n research $noun met"
# Announce each alert set once: the same data date and the same headlines are never shown again (a re-run is harmless).
$stamp = Join-Path (Split-Path -Parent $Path) "alerts_notified.txt"
$key = "$($data.asof)|" + (($alerts | ForEach-Object { "$($_.ticker):$($_.condition)" }) -join ",")
if (-not $DryRun -and (Test-Path -LiteralPath $stamp) -and ((Get-Content -LiteralPath $stamp -Raw -ErrorAction SilentlyContinue).Trim() -eq $key)) {
    Write-Output "Already announced for data date $($data.asof); no notification."; exit 0
}
# Windows cuts balloon text near 255 characters, so keep each headline short.
$lines = @($alerts | Select-Object -First $top | ForEach-Object { $h = [string]$_.headline; if ($h.Length -gt 70) { $h.Substring(0, 67) + "..." } else { $h } })
if ($n -gt $top) { $lines += "+$($n - $top) more in digest.md" }
$body = $lines -join "`n"

if ($DryRun) {
    Write-Output "[dry run] title: $title"
    Write-Output "[dry run] body:"
    $lines | ForEach-Object { Write-Output "  $_" }
    exit 0
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$icon = New-Object System.Windows.Forms.NotifyIcon
$icon.Icon = [System.Drawing.SystemIcons]::Information
$icon.BalloonTipTitle = $title
$icon.BalloonTipText = $body
$icon.Visible = $true
$icon.ShowBalloonTip(10000)
Start-Sleep -Seconds 11       # keep the icon alive while the balloon is visible, then remove it
$icon.Visible = $false
$icon.Dispose()
Set-Content -LiteralPath $stamp -Value $key -Encoding ASCII
