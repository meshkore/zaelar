#!/bin/zsh
# “The set never stops” without launchd (V2-417).
#
# WHY NOT LAUNCHD, written here so no one tries it blindly again: the repo lives under
# `~/Documents`, and macOS (TCC) denies a launchd agent access to that folder unless the
# operator manually grants Full Disk Access. Measured on 2026-08-28: the agent started and died with
# `127 · can't open input file` for a file that exists and is executable. `crontab` runs into the same issue.
# So the guardian is this loop, started detached from any session.
#
# WHAT IT COVERS: the supervisor dying (exception, OOM, a `kill`, or a set process taking the process
# down with it). It starts it again after `ESPERA_S`.
# WHAT IT DOES NOT COVER: a machine RESTART. That requires the `ops/` plist and disk permission
# — it is written and tested as far as TCC allows; it is an operator action, not something that can be automated.
#
# ONE AND ONLY ONE: there is one browser per set, and two supervisors running at once fight over the same
# tab and both runs fail. The lock is a file containing the PID, actually checked against the
# process — a stray file is not enough, because a killed guardian leaves its file behind forever.
set -u
cd "$(dirname "$0")/../../../../.." || exit 1     # → engine/

DIR="tests/runs/use_cases/supervisor"
mkdir -p "$DIR"
CANDADO="$DIR/keepalive.pid"
ESPERA_S="${ZAELAR_UC_ESPERA_S:-20}"

if [[ -f "$CANDADO" ]] && kill -0 "$(cat "$CANDADO" 2>/dev/null)" 2>/dev/null; then
  echo "ya hay un guardián vivo (pid $(cat "$CANDADO")) — no arranco un segundo"
  exit 0
fi
echo $$ > "$CANDADO"
trap 'rm -f "$CANDADO"' EXIT INT TERM

while true; do
  echo "[$(date '+%F %T')] levantando supervisor · HEAD $(git rev-parse --short HEAD 2>/dev/null)" \
    >> "$DIR/arranques.log"
  ./tests/use_cases/e2e/agent/supervisor_24x7.sh >> "$DIR/consola.log" 2>&1
  echo "[$(date '+%F %T')] el supervisor terminó (código $?) — reintento en ${ESPERA_S}s" \
    >> "$DIR/arranques.log"
  sleep "$ESPERA_S"
done
