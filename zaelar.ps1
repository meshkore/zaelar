# Zaelar launcher (Windows, PowerShell). Self-contained: everything lives under this folder.
# NATIVE — no make, no bash, no WSL, no Docker: only what Windows ships with (PowerShell) + Python.
#   .\zaelar.ps1            first run: check + setup + start.  After that: start.
#   .\zaelar.ps1 doctor     check requirements
#   .\zaelar.ps1 setup      create local .venv and install dependencies
#   .\zaelar.ps1 start      run Zaelar in the foreground (Ctrl-C quits) — http://localhost:43917
#   .\zaelar.ps1 up         start it in the BACKGROUND and return your prompt
#   .\zaelar.ps1 stop       stop it
#   .\zaelar.ps1 restart    stop + start in the background (this is how you load changed code)
#   .\zaelar.ps1 status     is it running? which build?
#   .\zaelar.ps1 update     git pull + re-setup
param([string]$cmd = "start")
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$BinDir = Join-Path $PSScriptRoot "bin"
$LkExe  = Join-Path $BinDir "livekit-server.exe"

$script:PyLauncher = $null
$script:PyVerArg   = $null

function Resolve-Py {
  # Prefer a Python known to have wheels for every pinned dependency (3.12/3.11/3.13) over whatever
  # generic "python"/"py" resolves to on PATH — a brand-new interpreter can be missing wheels for some
  # pinned packages (seen with Python 3.14 and the local-TTS phonemizer) for months after its release.
  if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($v in @("-3.12", "-3.11", "-3.13")) {
      & py $v -c "1" *>$null
      if ($LASTEXITCODE -eq 0) { $script:PyLauncher = "py"; $script:PyVerArg = $v; return }
    }
  }
  foreach ($c in @("python3.12", "python3.11", "python3.13", "python")) {
    if (Get-Command $c -ErrorAction SilentlyContinue) { $script:PyLauncher = $c; $script:PyVerArg = $null; return }
  }
  if (Get-Command py -ErrorAction SilentlyContinue) { $script:PyLauncher = "py"; $script:PyVerArg = $null; return }
  Write-Host "Zaelar needs Python 3.11+. Install it from https://python.org/downloads (check 'Add to PATH')."
  exit 1
}

function Invoke-Py {
  if ($script:PyVerArg) { & $script:PyLauncher $script:PyVerArg @args }
  else { & $script:PyLauncher @args }
}

function Invoke-Doctor { Resolve-Py; Invoke-Py scripts\doctor.py }

function Invoke-Setup {
  Resolve-Py
  Invoke-Py scripts\doctor.py
  if ($LASTEXITCODE -ne 0) { Write-Host "Fix the requirements above, then re-run .\zaelar.ps1 setup"; exit 1 }
  if (-not (Test-Path .venv)) {
    Write-Host "Creating self-contained environment (.venv)..."
    Invoke-Py -m venv .venv
  }
  & .\.venv\Scripts\python.exe -m pip install --upgrade pip | Out-Null
  Write-Host "Installing dependencies..."
  & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
  Write-Host "Setup complete. Start with:  .\zaelar.ps1 start"
}

# Native LiveKit media server binary — self-installed into .\bin\ (never system-wide, no Docker,
# no admin rights needed). Mirrors what `make install-livekit` does for macOS/Linux.
function Ensure-LiveKit {
  $existing = Get-Command livekit-server -ErrorAction SilentlyContinue
  if ($existing) { return $existing.Source }
  if (Test-Path $LkExe) { return $LkExe }

  Write-Host "Installing livekit-server (native binary, no Docker, one-time)..."
  New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
  $arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "arm64" } else { "amd64" }
  $release = Invoke-RestMethod -Uri "https://api.github.com/repos/livekit/livekit/releases/latest" -Headers @{ "User-Agent" = "zaelar-launcher" }
  $asset = $release.assets | Where-Object { $_.name -like "*windows_$arch.zip" } | Select-Object -First 1
  if (-not $asset) {
    Write-Host "Could not find a Windows livekit-server release asset."
    Write-Host "Download it manually from https://github.com/livekit/livekit/releases and place livekit-server.exe in:"
    Write-Host "  $BinDir"
    exit 1
  }
  $zip = Join-Path $env:TEMP "livekit-server-zaelar.zip"
  Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zip
  Expand-Archive -Path $zip -DestinationPath $BinDir -Force
  Remove-Item $zip -Force
  if (-not (Test-Path $LkExe)) { Write-Host "livekit-server.exe not found after extracting to $BinDir"; exit 1 }
  return $LkExe
}

function Get-PrimaryIP {
  # WebRTC needs a real (non-loopback) ICE candidate on some networks (hotspot/NAT) — best-effort,
  # falls back to loopback if it can't be determined.
  try {
    $cfg = Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq "Up" } | Select-Object -First 1
    if ($cfg -and $cfg.IPv4Address.IPAddress) { return $cfg.IPv4Address.IPAddress }
  } catch {}
  return "127.0.0.1"
}

function Wait-Port([int]$port, [int]$timeoutSec = 30) {
  $deadline = (Get-Date).AddSeconds($timeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      $client = New-Object System.Net.Sockets.TcpClient
      $client.Connect("127.0.0.1", $port)
      $client.Close()
      return $true
    } catch { Start-Sleep -Milliseconds 500 }
  }
  return $false
}

function Invoke-Start {
  if (-not (Test-Path .venv)) { Invoke-Setup }
  $port = if ($env:ZAELAR_PORT) { $env:ZAELAR_PORT } else { "43917" }
  $lk = Ensure-LiveKit

  # Free OUR OWN port from a stale previous run of Zaelar (never touches unrelated processes — only a
  # process actually listening on this port whose name looks like python).
  Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
    $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
    if ($p -and $p.ProcessName -match "python") { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
  }

  New-Item -ItemType Directory -Force -Path ".meshkore\logs" | Out-Null
  $nodeIp = Get-PrimaryIP
  Write-Host "-> LiveKit dev server (native binary, no Docker) - node-ip=$nodeIp"
  $lkProc = Start-Process -FilePath $lk `
    -ArgumentList @("--dev", "--bind", "127.0.0.1", "--node-ip=$nodeIp") `
    -PassThru -WindowStyle Hidden `
    -RedirectStandardOutput ".meshkore\logs\livekit-dev.log" `
    -RedirectStandardError ".meshkore\logs\livekit-dev.err.log"

  try {
    if (-not (Wait-Port 7880 30)) { Write-Host "WARN: LiveKit dev server did not come up in time - continuing anyway." }
    Start-Sleep -Seconds 2   # settle, so the embedded agent worker registers cleanly

    $env:BRAIN = "nucleo"
    $env:ZAELAR_ENGINE = "livekit"
    $env:PORT = $port
    Write-Host ""
    Write-Host "  -> open http://localhost:$port"
    Write-Host ""
    & .\.venv\Scripts\python.exe -m server
  } finally {
    if ($lkProc -and -not $lkProc.HasExited) { Stop-Process -Id $lkProc.Id -Force -ErrorAction SilentlyContinue }
  }
}

# Background lifecycle. Deliberately the SAME file the macOS/Linux launcher calls (scripts\zaelar.py, standard
# library only): one implementation, identical verbs on every platform, so a fix never lands on just one OS.
function Invoke-Lifecycle([string]$verb) {
  if (-not (Test-Path ".venv")) { Invoke-Setup }
  $venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
  if (-not (Test-Path $venvPy)) { Write-Host "No local environment yet. Run:  .\zaelar.ps1 setup"; exit 1 }
  & $venvPy "scripts\zaelar.py" $verb
  exit $LASTEXITCODE
}

switch ($cmd) {
  "doctor"  { Invoke-Doctor }
  "setup"   { Invoke-Setup }
  "start"   { Invoke-Start }
  "up"      { Invoke-Lifecycle "start" }
  "stop"    { Invoke-Lifecycle "stop" }
  "restart" { Invoke-Lifecycle "restart" }
  "status"  { Invoke-Lifecycle "status" }
  "update"  { git pull --ff-only; Invoke-Setup }
  default   { Write-Host "usage: .\zaelar.ps1 [doctor|setup|start|up|stop|restart|status|update]"; exit 1 }
}
