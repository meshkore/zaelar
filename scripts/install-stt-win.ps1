# zaelar — install the FREE LOCAL speech-to-text (faster-whisper) on Windows.
# After this, STT runs 100% on your PC (private, no per-use cost) and STT_PROVIDER=auto picks it automatically.
# The model itself is NOT bundled in git — it downloads once on first use (~150MB for "base").
# Run from PowerShell:  ./scripts/install-stt-win.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")              # -> zaelar\
$PY = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $PY)) { Write-Error "No encuentro .\.venv — crea el venv primero (ver docs/SETUP.md §1)"; exit 1 }

Write-Host "> Instalando faster-whisper (Whisper local) en el venv..."
& $PY -m pip install -q --upgrade faster-whisper

# Pre-descarga del modelo (opcional, evita el lag de la 1a transcripcion).
$MODEL = if ($env:WHISPER_MODEL) { $env:WHISPER_MODEL } else { "base" }   # tiny|base|small|medium|large-v3|turbo
Write-Host "> Pre-descargando el modelo '$MODEL' (una vez)..."
& $PY -c "import sys; from faster_whisper import WhisperModel; WhisperModel(sys.argv[1], device='auto', compute_type='int8'); print('OK modelo ' + sys.argv[1] + ' listo')" $MODEL

Write-Host ""
Write-Host "OK STT local instalado. Reinicia el servidor: con STT_PROVIDER=auto (o =whisper) usara Whisper local."
Write-Host "   Modelo por defecto: $MODEL - cambialo con WHISPER_MODEL en .env (mas grande = mas preciso y lento)."
