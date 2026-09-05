<#
Remove the Zaelar Local Daemon from this user's account.

THE STATE IS KEPT BY DEFAULT, and that is a deliberate asymmetry. Uninstalling is often a step in
troubleshooting, and throwing away the token and the folder allowlist turns "let me reinstall this" into "let
me set it all up again". -Purge is there for somebody who really means it, and it says what it deleted.

  .\uninstall.ps1
  .\uninstall.ps1 -Purge
#>
[CmdletBinding()]
param([switch]$Purge)

$ErrorActionPreference = 'Continue'
$TaskName = 'ZaelarDaemon'
$Prefix   = Join-Path $env:LOCALAPPDATA 'Zaelar'
$Startup  = [Environment]::GetFolderPath('Startup')

function Say { param($m) Write-Host "  $m" }

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Remove-Item (Join-Path $Startup 'Zaelar Daemon.lnk') -Force -ErrorAction SilentlyContinue
Get-Process -Name 'zaelar-daemon' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $Prefix 'bin') -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "OK  zaelar-daemon stopped and removed" -ForegroundColor Green
if ($Purge) {
  Remove-Item $Prefix -Recurse -Force -ErrorAction SilentlyContinue
  Say "purged: the token, the folder allowlist and the audit log are gone as well"
} else {
  Say "kept:   $Prefix  (your token, the folders you allowed, and the audit log)"
  Say "        run with -Purge to delete those too"
}
