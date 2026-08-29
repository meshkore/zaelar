#!/bin/sh
# Keep the Test Observatory reachable on 127.0.0.1:8765 at all times.
#
# The Observatory server (tests/platform/server.py) is run-scoped by design: each
# `python -m tests run` starts one for its run dir and it exits after the idle
# timeout. This loop fills the gaps: whenever nothing holds port 8765, it serves
# the LATEST durable run with an effectively infinite idle timeout. It never
# fights an active server — a new run's controlled handoff (/api/shutdown) stops
# this one cleanly, and while the port is busy the loop just waits.
ENGINE="$(cd "$(dirname "$0")/../.." && pwd)"
PORT=8765
while :; do
  if ! nc -z 127.0.0.1 "$PORT" 2>/dev/null; then
    RUN_DIR="$(ls -td "$ENGINE"/tests/runs/2* 2>/dev/null | head -1)"
    if [ -n "$RUN_DIR" ]; then
      "$ENGINE/.venv/bin/python" -m tests.platform.server \
        --run-dir "$RUN_DIR" --port "$PORT" --idle-timeout 315360000
    fi
  fi
  sleep 5
done
