#!/bin/sh
# The merge gate, LOCAL (operator's decision 2026-10-28: nothing runs on GitHub — no CI, no nightly).
# Run it from engine/ (or a worktree with `.venv` linked) on the branch you are about to merge:
#   ./tests/gate.sh                 # full gate: syntax, ruff, deterministic sweep, recorded bank
#   ./tests/gate.sh --impacted REF  # the cheap form while developing: only what the diff vs REF reaches
# Exit code is the gate's verdict. The wide sweep takes ~5 min on the operator's Mac.
set -e
cd "$(dirname "$0")/.."
PY=./.venv/bin/python
echo "== syntax sweep (the Dockerfile's COPY list — same as the release gate)"
$PY -m compileall -q nucleo memory voice server widgets bus config connectors observability i18n update
echo "== ruff (F + E9 only)"
./.venv/bin/ruff check .
if [ "$1" = "--impacted" ]; then
  echo "== deterministic sweep, impacted by the diff vs $2"
  ZAELAR_ATTENTION=always $PY tests/watchdog.py --impacted "$2"
  exit 0
fi
echo "== deterministic sweep (every model-free test, hang-aware)"
ZAELAR_ATTENTION=always $PY tests/watchdog.py --report "${GATE_REPORT:-/tmp/gate-watchdog.json}"
echo "== decision bank, recorded model (no key, seconds)"
ZAELAR_WORKSPACE="$(mktemp -d)" $PY -m tests.brain.runner --json "${GATE_BANK:-/tmp/gate-bank.json}"
echo "GATE GREEN"
