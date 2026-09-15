# One line, and the daemon is installed (V2-575 · P4).
#
#   irm https://raw.githubusercontent.com/meshkore/zaelar/main/daemon/packaging/get.ps1 | iex
#
# WHY A TERMINAL COMMAND IS THE MAIN PATH, and not a download button. The Mark of the Web is written by
# whatever SAVED the file — a browser stamps it, `Invoke-WebRequest` does not — so a file that arrives this
# way never triggers the SmartScreen "Windows protected your PC" panel, which is the single biggest reason an
# install of an unsigned tool gets abandoned. No Microsoft account, no code-signing certificate, no reputation
# to build up over months.
#
# ⚠️ IT DOES NOT TRUST THE DOWNLOAD BLINDLY. Piping a script into `iex` is exactly as safe as its origin and
# no safer, so: this script comes over https from the repository it belongs to, the binary comes from that
# repository's own release, and its SHA-256 is compared with the `SHA256SUMS-windows` the build published
# beside it. That is two files agreeing — enough to catch a corrupt download or an altered mirror, NOT
# provenance, since whoever can replace one can replace the other. Provenance needs a signature.
#
# NO ADMINISTRATOR. Anywhere.
$ErrorActionPreference = 'Stop'

$Repo    = if ($env:ZAELAR_DAEMON_REPO)     { $env:ZAELAR_DAEMON_REPO }     else { 'meshkore/zaelar' }
$RawBase = if ($env:ZAELAR_DAEMON_RAW_BASE) { $env:ZAELAR_DAEMON_RAW_BASE } else { "https://raw.githubusercontent.com/$Repo/main/daemon/packaging" }

function Say($m) { Write-Host "  $m" }
function Die($m) { Write-Host "X $m" -ForegroundColor Red; exit 1 }

if (-not $IsWindows -and $PSVersionTable.PSVersion.Major -ge 6) {
  Die 'this installer is for Windows. On macOS run the curl one-liner instead.'
}

# TLS 1.2 for Windows PowerShell 5.1, whose default still refuses github.com on some builds — the failure is
# an opaque "could not create SSL/TLS secure channel" that sends people hunting for a proxy problem.
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

# ── the newest DAEMON release, which is not the newest release ────────────────────────────────────────────
# The repository also tags the engine, so `releases/latest` regularly points at something carrying no daemon
# assets at all. Tags are filtered by prefix instead.
$Tag = $env:ZAELAR_DAEMON_TAG
if (-not $Tag) {
  try {
    $releases = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases?per_page=30" `
                                  -Headers @{ 'User-Agent' = 'zaelar-daemon-get' }
    $Tag = ($releases | Where-Object { $_.tag_name -like 'daemon-v*' } | Select-Object -First 1).tag_name
  } catch { }
}
if (-not $Tag) { Die 'could not find a published daemon release. Set ZAELAR_DAEMON_TAG to install a specific one.' }

$Asset = 'zaelar-daemon-windows.exe'
$Base  = "https://github.com/$Repo/releases/download/$Tag"
Write-Host ''
Write-Host "Zaelar Local Daemon · $Tag"
Write-Host ''

$Work = Join-Path ([IO.Path]::GetTempPath()) ("zaelar-daemon-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Work -Force | Out-Null
try {
  Say "downloading $Asset…"
  Invoke-WebRequest -Uri "$Base/$Asset" -OutFile (Join-Path $Work $Asset) -UseBasicParsing
  Invoke-WebRequest -Uri "$Base/SHA256SUMS-windows" -OutFile (Join-Path $Work 'SHA256SUMS') -UseBasicParsing

  # ── verify before anything is executed ──────────────────────────────────────────────────────────────────
  # While the file is still an inert blob in a temp directory: before it is moved, registered with the task
  # scheduler, or started.
  Say 'checking the download…'
  $line = Get-Content (Join-Path $Work 'SHA256SUMS') | Where-Object { $_ -match "\s$([regex]::Escape($Asset))$" } | Select-Object -First 1
  if (-not $line) { Die "$Asset is not listed in the published checksums for $Tag." }
  $expected = ($line -split '\s+')[0].ToLower()
  $actual = (Get-FileHash -Path (Join-Path $Work $Asset) -Algorithm SHA256).Hash.ToLower()
  if ($actual -ne $expected) {
    Die "checksum mismatch - the file that arrived is not the file that was built.`n    expected $expected`n    got      $actual"
  }
  Say 'checksum ok'

  # ── install with the same script the repository ships ───────────────────────────────────────────────────
  # Fetched from `main` rather than from the release, deliberately: it then shares this script's origin
  # exactly, so the trust decision the user already made by running this line is the only one being made.
  Say 'installing…'
  $installer = Join-Path $Work 'install.ps1'
  Invoke-WebRequest -Uri "$RawBase/windows/install.ps1" -OutFile $installer -UseBasicParsing
  & $installer (Join-Path $Work $Asset)

  # `iex` cannot pass an argument to the script it runs, so the destructive variant needs the scriptblock
  # form. Printing only the simple line would leave somebody guessing at a syntax that does not exist.
  Write-Host ''
  Write-Host '  To remove it later:'
  Write-Host "    irm $RawBase/windows/uninstall.ps1 | iex"
  Write-Host "    & ([scriptblock]::Create((irm $RawBase/windows/uninstall.ps1))) -Purge   # and forget the folders you chose"
  Write-Host ''
} finally {
  Remove-Item -Recurse -Force $Work -ErrorAction SilentlyContinue
}
