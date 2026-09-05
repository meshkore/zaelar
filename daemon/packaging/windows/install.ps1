<#
Install (or upgrade) the Zaelar Local Daemon on Windows, for the CURRENT USER ONLY.

NO ADMINISTRATOR, ON PURPOSE. A daemon whose whole job is to read one person's documents has no business
running elevated, and a UAC prompt is the single biggest reason an install gets abandoned. Everything lands in
this user's own LOCALAPPDATA and starts under their own logon, so it can never reach another account's files
even if every check inside it failed at once.

RE-RUNNING IT IS THE UPGRADE PATH. Stop, replace, start — so "deploy a new version" is the same command as
"install", and there is no second procedure to get wrong. The state directory, which holds the token and the
folders the user chose, is never touched.

  .\install.ps1                      use the artifact next to this script, or the newest in dist\daemon\
  .\install.ps1 -Artifact <path>     use a specific one (a onefile .exe or a .pyz)

If PowerShell refuses to run this at all, it is the execution policy and not the script:
  powershell -ExecutionPolicy Bypass -File .\install.ps1
#>
[CmdletBinding()]
param([string]$Artifact)

$ErrorActionPreference = 'Stop'
$TaskName = 'ZaelarDaemon'
$Here     = Split-Path -Parent $MyInvocation.MyCommand.Path
$Prefix   = Join-Path $env:LOCALAPPDATA 'Zaelar'
$BinDir   = Join-Path $Prefix 'bin'
$LogDir   = Join-Path $Prefix 'logs'
$Target   = Join-Path $BinDir 'zaelar-daemon.exe'

function Say  { param($m) Write-Host "  $m" }
function Die  { param($m) Write-Host "X $m" -ForegroundColor Red; exit 1 }

# ── find something to install ─────────────────────────────────────────────────────────────────────────────
# The onefile .exe is preferred because it carries its own interpreter: nothing else has to be present on the
# machine. The .pyz is the fallback and needs a Python, which is why the check below is a check and not an
# assumption — a logon task that cannot find its interpreter fails at the NEXT LOGIN, with the user nowhere
# near a console to see why.
if (-not $Artifact) {
  $candidates = @(
    (Join-Path $Here 'zaelar-daemon.exe'),
    (Join-Path $Here 'zaelar-daemon.pyz'),
    (Join-Path $Here '..\..\..\dist\daemon\zaelar-daemon.exe'),
    (Join-Path $Here '..\..\..\dist\daemon\zaelar-daemon.pyz')
  )
  $Artifact = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $Artifact -or -not (Test-Path $Artifact)) {
  Die "no artifact found. Build one: python daemon\packaging\build.py"
}
$Artifact = (Resolve-Path $Artifact).Path

$PythonExe = $null
if ($Artifact -like '*.pyz') {
  foreach ($name in @('py', 'python', 'python3')) {
    $found = Get-Command $name -ErrorAction SilentlyContinue
    if ($found) { $PythonExe = $found.Source; break }
  }
  if (-not $PythonExe) { Die "$Artifact needs a Python and there is none on PATH. Install the .exe build instead." }
  $ok = & $PythonExe -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)"
  if ($LASTEXITCODE -ne 0) { Die "the Python on PATH is older than 3.11, which the daemon requires." }
}

New-Item -ItemType Directory -Force -Path $BinDir, $LogDir | Out-Null

# ── stop whatever is running, so the file can be replaced ─────────────────────────────────────────────────
# Each of these is allowed to fail: "it was not running" is a fine outcome for a stop, and the daemon may also
# have been started from a console, which the task scheduler knows nothing about.
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Get-Process -Name 'zaelar-daemon' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

# ── install the artifact ──────────────────────────────────────────────────────────────────────────────────
if ($Artifact -like '*.pyz') {
  $pyz = Join-Path $BinDir 'zaelar-daemon.pyz'
  Copy-Item -Path $Artifact -Destination $pyz -Force
  Unblock-File -Path $pyz -ErrorAction SilentlyContinue
  # A one-line launcher rather than calling Python from the task: the task names ONE program, so upgrading from
  # .pyz to .exe later does not need a different task definition.
  $Target = Join-Path $BinDir 'zaelar-daemon.cmd'
  "@echo off`r`n`"$PythonExe`" `"$pyz`" %*" | Set-Content -Path $Target -Encoding ASCII
  Say "installed the portable build (needs $PythonExe)"
} else {
  Copy-Item -Path $Artifact -Destination $Target -Force
  # The Mark of the Web: anything that arrived through a browser is blocked, and the failure is a dialog the
  # user cannot dismiss into a working state. Clearing it on a file THEY just chose to install is the same
  # consent they already gave; it is not a substitute for signing, which is a release step.
  Unblock-File -Path $Target -ErrorAction SilentlyContinue
  Say "installed the standalone build (carries its own Python)"
}

# ── register it to start at logon ─────────────────────────────────────────────────────────────────────────
# A scheduled task is preferred over a Startup shortcut because it can run with no window and can be restarted
# if it stops. Registering one is allowed without elevation for a task that runs as the user registering it —
# "allowed" being a matter of local policy, which is why the fallback below exists rather than a message
# telling somebody to go and find an administrator.
$registered = $false
try {
  $action    = New-ScheduledTaskAction -Execute $Target
  $trigger   = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
  $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
  $settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                 -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
                 -ExecutionTimeLimit ([TimeSpan]::Zero) -Hidden
  Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal `
                         -Settings $settings -Description 'Zaelar Local Daemon (per-user, loopback only)' | Out-Null
  Start-ScheduledTask -TaskName $TaskName
  $registered = $true
  Say "starts:   at logon, as a scheduled task"
} catch {
  Say "the task scheduler refused ($($_.Exception.Message.Split([Environment]::NewLine)[0])) — using the Startup folder instead"
}

if (-not $registered) {
  $startup  = [Environment]::GetFolderPath('Startup')
  $shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $startup 'Zaelar Daemon.lnk'))
  $shortcut.TargetPath  = $Target
  $shortcut.WindowStyle = 7          # minimized, so it does not sit on top of whatever the user is doing
  $shortcut.Description = 'Zaelar Local Daemon'
  $shortcut.Save()
  Start-Process -FilePath $Target -WindowStyle Hidden
  Say "starts:   at logon, from the Startup folder"
}

# ── say what happened, and check it rather than assume ────────────────────────────────────────────────────
Start-Sleep -Seconds 1
$version = try { (& $Target version 2>$null) } catch { '?' }
Write-Host ""
Write-Host "OK  zaelar-daemon $version installed for $env:USERNAME" -ForegroundColor Green
Say "program:  $Target"
Say "state:    $Prefix  (the token and the folders you allow)"
Say "log:      $LogDir"
Write-Host ""
Say "It can read NOTHING until you choose folders — that is the point of the wizard in Zaelar."
Say "From a console: `"$Target`" status | allow `"$env:USERPROFILE\Documents`" | deny ..."
Write-Host ""
Say "It listens on 127.0.0.1 only, so Windows Firewall will not ask you about it. If something does ask"
Say "for permission to accept connections from the network, that is not this."
