#!/bin/sh
# scripts/uc-loop.sh — keep the use-case battery measuring, unattended.
#
# WHY A KEEPALIVE AND NOT A CRON THAT RUNS THE BATTERY: the supervisor is already a loop. What dies is the
# PROCESS — a broker hiccup, a machine sleeping, a lab that had to be restarted. So the schedule's job is not
# "run a round every N minutes" (that would stack overlapping batteries and multiply the bill); it is "if the
# supervisor is not alive, start it, and never start a second one".
#
# The lock is the process itself: `pgrep -f` on the module path. It is the only check that survives a reboot,
# a kill -9 and a full disk, which a pidfile does not.
#
# Refuses to start when the providers are down, and says so: a battery with no brain produces INFRA rounds at
# ~6 min each and a bill for nothing (measured 2026-08-30 — every worker case INFRA while both wallets were
# empty). The probe is one cheap call.
set -eu

ENGINE="$(cd "$(dirname "$0")/.." && pwd)"
PY="$ENGINE/.venv/bin/python"
LOG="$ENGINE/tests/runs/use_cases/loop.log"
MOD="tests.use_cases.e2e.agent.supervisor"

say() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

if pgrep -f "$MOD" > /dev/null 2>&1; then
  exit 0                       # already measuring: do not start a second battery
fi

# Is there a brain? Without it, the battery only produces INFRA and incurs charges.
if ! "$PY" - <<'PY' >/dev/null 2>&1
import json, os, sys, urllib.request
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv
load_dotenv(".meshkore/credentials/zaelar.env", override=True)
for url, key, model in (
    ("https://api.deepseek.com/chat/completions", os.getenv("DEEPSEEK_API_KEY"), "deepseek-chat"),
    ("https://api.aimlapi.com/v1/chat/completions", os.getenv("AIMLAPI_KEY"), "deepseek/deepseek-v4-flash"),
):
    req = urllib.request.Request(url, data=json.dumps(
        {"model": model, "messages": [{"role": "user", "content": "ok"}], "max_tokens": 2}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key or ''}",
                 "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120"})
    try:
        urllib.request.urlopen(req, timeout=25).read()
        sys.exit(0)
    except Exception:
        continue
sys.exit(1)
PY
then
  say "sin cerebro (las dos carteras caídas) — no arranco: una batería sin cerebro sólo produce INFRA y factura"
  exit 0
fi

# The labs must be up; `up` is idempotent and leaves an already-running one alone.
for lab in es us; do "$PY" -m tests.use_cases.lab up "$lab" >/dev/null 2>&1 || true; done

say "arrancando la batería (fase ${UC_PHASE:-1})"
cd "$ENGINE"
exec "$PY" -m "$MOD" --phase "${UC_PHASE:-1}" --continuo --vueltas 0 >> "$LOG" 2>&1
