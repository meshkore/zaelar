# zaelar — install the FREE LOCAL text-to-speech (Kokoro) on Windows. After this, TTS_PROVIDER=kokoro runs 100% on
# your PC (private, no per-use cost). Spanish voices. The default TTS stays Aura-2 (better es+en); this just makes
# the local option available. The voice model (~300MB) downloads once on first use.
# Run from PowerShell:  ./scripts/install-tts-win.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")              # -> zaelar\
$PY = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $PY)) { Write-Error "No encuentro .\.venv — crea el venv primero (ver docs/SETUP.md §1)"; exit 1 }

Write-Host "> Instalando Kokoro (TTS local) en el venv..."
& $PY -m pip install -q --upgrade kokoro-onnx onnxruntime

Write-Host ""
Write-Host "OK TTS local (Kokoro) instalado. El modelo (~300MB) se baja solo en la 1a sintesis."
Write-Host "   Actívalo desde el config de /architecture, o con TTS_PROVIDER=kokoro en .env. Voces: ef_dora (f), em_alex (m)."
