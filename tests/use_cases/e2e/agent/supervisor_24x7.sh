#!/bin/zsh
# The studio NEVER STOPS — startup wrapper for the supervisor (V2-417).
#
# The supervisor is already an infinite loop that does not die after one round and reloads itself when its
# own code changes. What it does NOT know how to do is come back into existence: if the process dies (an
# update, a `killall python`, a machine restart), there is no one to bring it back up. launchd does that
# with `KeepAlive`; this script is what launchd starts, and its only job is to put the world in order
# BEFORE entering the loop.
#
# Bringing the studios up here rather than inside the supervisor is deliberate: after a restart there is no
# live studio, and a supervisor that starts against dead ports does not fail — it measures and writes an
# INFRA row for every scenario in the rotation until someone looks. A loop that produces garbage at full
# speed is worse than a stopped one, because the stopped one is noticeable.
set -u
cd "$(dirname "$0")/../../../.." || exit 1        # → engine/

LOGS="tests/runs/use_cases/supervisor"
mkdir -p "$LOGS"

echo "[$(date '+%F %T')] arrancando · HEAD $(git rev-parse --short HEAD 2>/dev/null)" >> "$LOGS/arranques.log"

# Studios, idempotent: `up` on one that is already live leaves it alone (preserving its port, memory, and profile).
./.venv/bin/python -m tests.use_cases.lab up all >> "$LOGS/arranques.log" 2>&1

# ZAELAR_UC_CAFFEINATE=0 to let the Mac sleep. By default, sleep due to INACTIVITY is prevented
# (`caffeinate -i`), which is the only thing separating “running for 24 hours” from “running until you go
# out to dinner.” It does not prevent sleep when the lid is closed: that remains the operator’s physical decision.
if [[ "${ZAELAR_UC_CAFFEINATE:-1}" == "1" ]] && command -v caffeinate >/dev/null; then
  exec caffeinate -i ./.venv/bin/python -m tests.use_cases.e2e.agent.supervisor
fi
exec ./.venv/bin/python -m tests.use_cases.e2e.agent.supervisor
