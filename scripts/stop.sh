#!/usr/bin/env bash
# stop.sh — DELEGATOR. The stopping logic now lives in `scripts/zaelar.py` (2026-08-12).
#
# Why it was moved: this script was bash with lsof/pkill/pgrep, so it did not work on Windows—and zaelar is a PUBLIC
# project that people self-host. It also only freed port 43917 and never 44317 (the HTTPS listener), so half an
# instance survived every stop, and it did not escalate to kill when the process ignored SIGTERM (which really
# happens: a hung voice-worker thread does not die from a TERM).
#
# This file is retained so as not to break anyone who calls it by name. Recommended entry point:
#     make stop            (or, without make:  python scripts/zaelar.py stop)
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f "$HERE/Makefile" && -d "$HERE/nucleo" ]] || { echo "✗ no parece el repo de zaelar ($HERE)"; exit 1; }
PY="$HERE/.venv/bin/python"; [[ -x "$PY" ]] || PY="$(command -v python3 || command -v python)"
exec "$PY" "$HERE/scripts/zaelar.py" stop
