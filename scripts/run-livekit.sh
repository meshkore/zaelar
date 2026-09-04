#!/usr/bin/env bash
# zaelar over LiveKit (INI-012) — starts the new voice stack:
#   1) LiveKit dev server   2) agent worker (EMBEDDED voice/engine)   3) zaelar web server (FastAPI)
# Ctrl-C tears everything down. The LiveKit server uses the NATIVE BINARY (without Docker) if installed
# (`make install-livekit` / `brew install livekit`); Docker is only an optional FALLBACK.
#
# Usage:  bash scripts/run-livekit.sh   (default «Colmena» nucleo brain; override with BRAIN=direct/local)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$HERE/.venv/bin/python"
LK_CONTAINER="zaelar-livekit"
: "${BRAIN:=nucleo}"
export BRAIN

AGENT_PID=""; WEB_PID=""; LK_PID=""; LK_MODE=""; DAEMON_PID=""
cleanup() {
  echo; echo "shutting down…"
  [[ -n "$AGENT_PID" ]] && kill "$AGENT_PID" 2>/dev/null || true
  [[ -n "$WEB_PID" ]] && kill "$WEB_PID" 2>/dev/null || true
  [[ -n "$DAEMON_PID" ]] && kill "$DAEMON_PID" 2>/dev/null || true
  [[ -n "$LK_PID" ]] && kill "$LK_PID" 2>/dev/null || true
  [[ "$LK_MODE" == "docker" ]] && docker rm -f "$LK_CONTAINER" >/dev/null 2>&1 || true
  true
}
trap cleanup EXIT INT TERM

# LiveKit dev server: preferred NATIVE BINARY (without Docker); Docker only as a fallback.
mkdir -p "$HERE/.meshkore/logs"

# STABILITY (V2-036): sweep ORPHANED browsers/bridges from previous launches (a server kill -9 leaves
# Playwright's chrome-headless-shell and the node bridge detached, consuming CPU/RAM and saturating the machine). Only touches
# Playwright's chrome-headless-shell (NOT the operator's Google Chrome) and zaelar's WhatsApp bridge.
pkill -f "chrome-headless-shell" 2>/dev/null || true
pkill -f "widgets/navegador/bridge\|connectors/whatsapp/bridge/bridge.js" 2>/dev/null || true
# V2-038: sweep ORPHANED Brain Workers (claude --print in streaming mode) from a previous crash. The signature
# `--input-format stream-json --output-format stream-json` is exclusive to our workers → does NOT touch an operator's
# interactive `claude`. §v3·L (the RAM sweep covers a clean restart; this covers kill -9).
pkill -f "input-format stream-json --output-format stream-json" 2>/dev/null || true

# SINGLE INSTANCE (recurring fix 2026-07-16): a previous `make run` that did not receive Ctrl-C (terminal closed,
# kill -9, started in the background) leaves `livekit-server` and/or the web server ALIVE. The next `make run`
# starts a new `livekit-server` that CANNOT bind 7880 (it dies silently in the background), but the readiness probe
# responds against the OLD zombie → the web server attaches to the wedged LiveKit →
# `wait_pc_connection timed out`, "Lost the audio connection", zero STT. Reap the previous stack BEFORE
# starting and wait for 7880 to become FREE, so the new livekit-server is the one actually listening.
SELF_PID=$$
for pid in $(pgrep -f "scripts/run-livekit.sh" 2>/dev/null || true); do
  [[ "$pid" != "$SELF_PID" ]] && kill "$pid" 2>/dev/null || true   # its EXIT trap tears down its children (livekit + web)
done
pkill -f "livekit-server --dev" 2>/dev/null || true   # OUR orphaned livekit-server (without its script; any node-ip)
_web_pids="$(lsof -ti tcp:43917 -sTCP:LISTEN 2>/dev/null || true)"      # previous web server owning 43917
[[ -n "$_web_pids" ]] && kill $_web_pids 2>/dev/null || true
# SPLIT-BRAIN (fix 2026-07-16): the reap above only kills the OWNER of 43917. An ORPHANED `python -m server`
# (PPID=1, its run-livekit.sh has already died) that is NO LONGER the owner of 43917 —because a newer stack took it—
# SURVIVES, but its EMBEDDED LiveKit worker remains REGISTERED on 7880 → the dev server dispatches voice jobs to it
# → the turn runs on the ZOMBIE while the frontend's /events (SSE) hangs off the LIVE process → "does not close widgets", the
# brain cannot see the canvas, and the task dies. Reap ALL previous `python -m server` processes (SIGTERM and, if ignored
# —observed live—, SIGKILL); the one started below will be the only one with a registered worker.
for pid in $(pgrep -f "[Pp]ython -m server" 2>/dev/null || true); do kill "$pid" 2>/dev/null || true; done
sleep 0.5
for pid in $(pgrep -f "[Pp]ython -m server" 2>/dev/null || true); do kill -9 "$pid" 2>/dev/null || true; done
# Same sweep for the LOCAL DAEMON (V2-575). It holds the user's folder allowlist and a persistent browser profile,
# so an orphan from a previous launch keeps 45817 and the new one dies on a silent EADDRINUSE — the exact failure
# mode this whole reaping section exists for, one process further along.
for pid in $(pgrep -f "[Pp]ython -m daemon" 2>/dev/null || true); do kill "$pid" 2>/dev/null || true; done
# wait for 7880 to become FREE (up to ~6s) — otherwise the probe below re-detects the zombie and we return to the bug
for _ in $(seq 1 12); do nc -z 127.0.0.1 7880 2>/dev/null || break; sleep 0.5; done

# node-ip: we do NOT pin it (self-healing on network changes — fix 2026-07-29). LiveKit/pion ENUMERATES LIVE
# interfaces and gathers their ICE host-candidates AT THE MOMENT of each new PeerConnection (not once at startup) → a
# connection made AFTER switching wifi/hotspot/a-friend's-house automatically advertises the CURRENT IP, without restarting.
# PINNING `--node-ip` at startup (what we used to do) specifically DISABLED that auto-discovery: LiveKit continued
# advertising the IP detected at startup even though it no longer existed on any interface → 'wait_pc_connection timed out'
# on EVERY network change (recurring incident 2026-07-28: 3 outages in one day while moving between networks).
# NOTE — this is NOT the loopback case: `--node-ip=127.0.0.1` DOES fail (the embedded pion agent does not gather a loopback
# candidate → there is no ICE pair, confirmed by the LiveKit community); therefore we do NOT set loopback, simply do NOT
# pin anything and leave enumeration dynamic. Signaling remains on `--bind 127.0.0.1` (private, not LAN).
# Power-user escape hatch / unusual environments: `ZAELAR_LIVEKIT_NODE_IP=<ip>` restores the old pin.
# PRODUCTION (real deploy, not local): LiveKit Cloud or coturn/Cloudflare TURN → relay candidate with a stable IP,
# independent of the node IP and the client's NAT. See zaelar-deploy.md. Detail: research 2026-07-29.
LK_NODE_IP_ARG=""
if [[ -n "${ZAELAR_LIVEKIT_NODE_IP:-}" ]]; then
  LK_NODE_IP_ARG="--node-ip=${ZAELAR_LIVEKIT_NODE_IP}"
fi

# AUTO-INSTALL (self-contained first run, without manual steps): if there is no native binary, attempts to install it
# BEFORE falling back to Docker/error — macOS via brew, Linux via the official installer. Silent if already present.
if ! command -v livekit-server >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "▶ instalando livekit-server (brew, una vez)…"
    brew install livekit >/dev/null 2>&1 || true
  elif [[ "$(uname -s)" == "Linux" ]]; then
    echo "▶ instalando livekit-server (get.livekit.io, una vez)…"
    curl -sSL https://get.livekit.io | bash >/dev/null 2>&1 || true
  fi
fi

if command -v livekit-server >/dev/null 2>&1; then
  LK_MODE="native"
  echo "▶ servidor LiveKit dev (binario nativo, sin Docker) · node-ip=${ZAELAR_LIVEKIT_NODE_IP:-dinámico (auto-red)} ..."
  livekit-server --dev --bind 127.0.0.1 $LK_NODE_IP_ARG >"$HERE/.meshkore/logs/livekit-dev.log" 2>&1 &
  LK_PID=$!
elif command -v docker >/dev/null 2>&1; then
  LK_MODE="docker"
  echo "▶ servidor LiveKit dev (Docker · fallback; instala el binario con 'make install-livekit' para evitarlo)…"
  docker rm -f "$LK_CONTAINER" >/dev/null 2>&1 || true
  docker run -d --rm --name "$LK_CONTAINER" \
    -p 7880:7880 -p 7881:7881 -p 7882:7882/udp \
    livekit/livekit-server --dev --bind 0.0.0.0 --node-ip=127.0.0.1 >/dev/null
else
  echo "✗ No hay ni 'livekit-server' (nativo) ni Docker. Instala el binario nativo:"
  echo "    make install-livekit   (macOS: brew install livekit · Linux: curl -sSL https://get.livekit.io | bash)"
  echo "    Windows: descarga de https://github.com/livekit/livekit/releases"
  exit 1
fi
# Wait until LiveKit is truly READY for the embedded worker's agent registration — not just the TCP port open.
# `nc -z` succeeds the instant the socket binds, but the agent service may not be up; if the worker registers in
# that window it can SILENTLY fail to register (seen 2026-07-07: 0 workers registered → NO agent ever joins a room
# → dead voice across the ENTIRE system). Probe HTTP + add a settle margin before starting the web server.
for _ in $(seq 1 60); do curl -sf -m1 -o /dev/null "http://127.0.0.1:7880/" 2>/dev/null && break; nc -z 127.0.0.1 7880 2>/dev/null && break; sleep 0.5; done
sleep 2   # settle: let the agent service finish coming up so worker registration lands (avoids the startup race)
echo "  ws://127.0.0.1:7880 (devkey/secret)"

# LOCAL DAEMON (V2-575): the user's files and the real browser that passes CAPTCHAs. Standard library only, so it
# runs on the venv without installing anything. ADDITIVE — the engine keeps its own in-process browser, so if this
# never comes up the product is exactly what it is today; that is why nothing below waits on it or checks it.
echo "▶ zaelar-daemon (ficheros + navegador local)…"
( cd "$HERE" && exec "$PY" -m daemon ) >"$HERE/.meshkore/logs/daemon.log" 2>&1 & DAEMON_PID=$!

echo "▶ servidor web zaelar (worker LiveKit EMBEBIDO, BRAIN=$BRAIN)…"
# The worker runs inside this process (ZAELAR_ENGINE=livekit → server lifespan mounts the AgentServer THREAD).
# There is no separate worker process: this way it shares the bus/observer-SSE, central memory, orchestrator loop, and
# brain_notes mailbox with the «Colmena» brain (nucleo/).
( cd "$HERE" && ZAELAR_ENGINE=livekit exec "$PY" -m server ) & WEB_PID=$!

echo
echo "  ➜  abre  http://localhost:43917"
echo
wait
