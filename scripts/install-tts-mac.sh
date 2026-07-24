#!/usr/bin/env bash
# zaelar — install the FREE LOCAL text-to-speech (Kokoro) on macOS. After this, TTS_PROVIDER=kokoro runs 100% on
# your Mac (private, no per-use cost). Spanish voices (no es↔en codeswitching — for that keep the default Aura-2).
# The voice model (~300MB) downloads once on first use. NOTE: the default TTS stays Aura-2 (better es+en); this
# just makes the local option available — switch to it from the ⚙ config (or TTS_PROVIDER=kokoro).
set -euo pipefail
cd "$(dirname "$0")/.."                                   # → zaelar/
PY="./.venv/bin/python"
[ -x "$PY" ] || { echo "✗ No encuentro ./.venv — crea el venv primero (ver docs/SETUP.md §1)"; exit 1; }

echo "▸ Instalando Kokoro (TTS local) en el venv…"
"$PY" -m pip install -q --upgrade kokoro-onnx onnxruntime

echo
echo "✓ TTS local (Kokoro) instalado. El modelo de voz (~300MB) se baja solo en la 1ª síntesis."
echo "  Actívalo desde el ⚙ de /architecture, o con TTS_PROVIDER=kokoro en .env. Voces: ef_dora (f), em_alex (m)."
