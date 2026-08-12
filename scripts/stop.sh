#!/usr/bin/env bash
# stop.sh — DELEGADOR. La lógica de parar vive ahora en `scripts/zaelar.py` (2026-08-12).
#
# Por qué se movió: este script era bash con lsof/pkill/pgrep, así que en Windows no servía —y zaelar es un proyecto
# PÚBLICO que la gente auto-hospeda. Además solo liberaba el puerto 43917 y nunca el 44317 (el listener HTTPS), con
# lo que media instancia sobrevivía a cada parada, y no escalaba a kill cuando el proceso ignoraba SIGTERM (que pasa
# de verdad: un hilo del worker de voz colgado no muere con un TERM).
#
# Se conserva este fichero para no romper a nadie que lo llame por su nombre. Entrada recomendada:
#     make stop            (o, sin make:  python scripts/zaelar.py stop)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f "$HERE/Makefile" && -d "$HERE/nucleo" ]] || { echo "✗ no parece el repo de zaelar ($HERE)"; exit 1; }
PY="$HERE/.venv/bin/python"; [[ -x "$PY" ]] || PY="$(command -v python3 || command -v python)"
exec "$PY" "$HERE/scripts/zaelar.py" stop
