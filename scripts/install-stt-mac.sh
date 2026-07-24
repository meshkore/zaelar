#!/usr/bin/env bash
# zaelar — install the FREE LOCAL speech-to-text on macOS (Apple Silicon → MLX Whisper, GPU/Neural Engine).
# After this, STT runs 100% on your Mac (private, no per-use cost) and STT_PROVIDER=auto picks it automatically.
# The model itself is NOT bundled in git — it downloads once (~1.5GB for large-v3-turbo) and caches in ~/.cache.
set -euo pipefail
cd "$(dirname "$0")/.."                                   # → zaelar/
PY="./.venv/bin/python"
[ -x "$PY" ] || { echo "✗ No encuentro ./.venv — crea el venv primero (ver docs/SETUP.md §1)"; exit 1; }

# Pipecat's whisper module needs BOTH faster-whisper and (on Apple Silicon) mlx-whisper to import.
echo "▸ Instalando Whisper local (mlx-whisper + faster-whisper) en el venv…"
"$PY" -m pip install -q --upgrade faster-whisper mlx-whisper

# Pre-descarga del modelo MLX (opcional pero recomendado: evita el lag de la 1ª transcripción).
MODEL="${WHISPER_MODEL_MLX:-mlx-community/whisper-large-v3-turbo}"   # multilingüe, rápido en Apple Silicon
echo "▸ Pre-descargando el modelo '$MODEL' (una vez)…"
"$PY" - "$MODEL" <<'PY'
import sys
try:
    from huggingface_hub import snapshot_download
    snapshot_download(sys.argv[1])
    print(f"✓ Modelo '{sys.argv[1]}' descargado y cacheado (~/.cache/huggingface).")
except Exception as e:
    print(f"· No pude pre-descargar ({e}). No pasa nada: se bajará solo en la 1ª transcripción.")
PY

echo
echo "✓ STT local instalado (MLX, Apple Silicon). Reinicia el servidor: con STT_PROVIDER=auto ya usa Whisper local."
echo "  Modelo: $MODEL — cámbialo con WHISPER_MODEL_MLX en .env (tiny/medium/large-v3/turbo)."
