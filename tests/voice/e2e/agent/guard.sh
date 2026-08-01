#!/usr/bin/env bash
# Cron guard: keep the test system ALIVE without a human.
#   1) zaelar UP on :43917 (native LiveKit + «Colmena» nucleo) — restart detached if down.
#   2) the overnight test loop running — start detached if not.
# Idempotent + detached; safe to run repeatedly. Logs to tests/runs/agent/guard.log.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
LOG="$HERE/tests/runs/agent/guard.log"
mkdir -p "$HERE/tests/runs/agent"
ts() { date +"%Y-%m-%d %H:%M:%S"; }

# 1) zaelar
if ! nc -z 127.0.0.1 43917 2>/dev/null; then
  echo "[$(ts)] zaelar down → starting (make run, detached)" >> "$LOG"
  ( cd "$HERE" && nohup make run >> "$HERE/tests/runs/agent/zaelar.log" 2>&1 & )
  # readiness: wait for the API to actually answer (not just the port), like overnight.sh
  for _ in $(seq 1 90); do curl -sf http://127.0.0.1:43917/api/livekit >/dev/null 2>&1 && break; sleep 1; done
else
  echo "[$(ts)] zaelar up" >> "$LOG"
fi

# 2) overnight loop
if ! pgrep -f "tests/voice/e2e/agent/overnight.sh" >/dev/null 2>&1; then
  echo "[$(ts)] overnight loop down → starting (detached)" >> "$LOG"
  ( cd "$HERE" && nohup bash tests/voice/e2e/agent/overnight.sh >> "$HERE/tests/runs/agent/overnight.log" 2>&1 & )
else
  echo "[$(ts)] overnight loop running" >> "$LOG"
fi
