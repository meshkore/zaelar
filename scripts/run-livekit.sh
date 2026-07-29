#!/usr/bin/env bash
# zaelar sobre LiveKit (INI-012) — levanta el stack de voz nuevo:
#   1) servidor LiveKit dev   2) agent worker (voice/engine EMBEBIDO)   3) servidor web zaelar (FastAPI)
# Ctrl-C lo tira todo. El servidor LiveKit usa el BINARIO NATIVO (sin Docker) si está instalado
# (`make install-livekit` / `brew install livekit`); Docker es solo un FALLBACK opcional.
#
# Uso:  bash scripts/run-livekit.sh   (cerebro «Colmena» nucleo por defecto; override con BRAIN=direct/local)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$HERE/.venv/bin/python"
LK_CONTAINER="zaelar-livekit"
: "${BRAIN:=nucleo}"
export BRAIN

AGENT_PID=""; WEB_PID=""; LK_PID=""; LK_MODE=""
cleanup() {
  echo; echo "shutting down…"
  [[ -n "$AGENT_PID" ]] && kill "$AGENT_PID" 2>/dev/null || true
  [[ -n "$WEB_PID" ]] && kill "$WEB_PID" 2>/dev/null || true
  [[ -n "$LK_PID" ]] && kill "$LK_PID" 2>/dev/null || true
  [[ "$LK_MODE" == "docker" ]] && docker rm -f "$LK_CONTAINER" >/dev/null 2>&1 || true
  true
}
trap cleanup EXIT INT TERM

# Servidor LiveKit dev: BINARIO NATIVO preferido (sin Docker); Docker solo como fallback.
mkdir -p "$HERE/.meshkore/logs"

# ESTABILIDAD (V2-036): barre navegadores/bridges HUÉRFANOS de arranques anteriores (un kill -9 del server deja
# chrome-headless-shell de Playwright y el node bridge sueltos, que consumen CPU/RAM y saturan el equipo). Solo toca
# el chrome-headless-shell de Playwright (NO el Google Chrome del operador) y el bridge de WhatsApp de zaelar.
pkill -f "chrome-headless-shell" 2>/dev/null || true
pkill -f "widgets/navegador/bridge\|connectors/whatsapp/bridge/bridge.js" 2>/dev/null || true
# V2-038: barre Brain Workers HUÉRFANOS (claude --print en modo streaming) de un crash previo. La firma
# `--input-format stream-json --output-format stream-json` es exclusiva de nuestros workers → NO toca un `claude`
# interactivo del operador. §v3·L (el barrido en RAM cubre el reinicio limpio; esto, el kill -9).
pkill -f "input-format stream-json --output-format stream-json" 2>/dev/null || true

# INSTANCIA ÚNICA (fix recurrente 2026-07-16): un `make run` anterior que no recibió Ctrl-C (terminal cerrada,
# kill -9, arrancado en background) deja el `livekit-server` y/o el server web VIVOS. El siguiente `make run`
# arranca un `livekit-server` nuevo que NO puede bindear el 7880 (muere en silencio en background), pero el probe
# de readiness responde contra el VIEJO zombi → el server web se engancha al LiveKit wedgeado →
# `wait_pc_connection timed out`, "Lost the audio connection", cero STT. Reapamos el stack anterior ANTES de
# arrancar y esperamos a que el 7880 quede LIBRE, para que el nuevo livekit-server sea el que de verdad escucha.
SELF_PID=$$
for pid in $(pgrep -f "scripts/run-livekit.sh" 2>/dev/null || true); do
  [[ "$pid" != "$SELF_PID" ]] && kill "$pid" 2>/dev/null || true   # su trap EXIT tira a sus hijos (livekit + web)
done
pkill -f "livekit-server --dev" 2>/dev/null || true   # livekit-server NUESTRO huérfano (sin su script; cualquier node-ip)
_web_pids="$(lsof -ti tcp:43917 -sTCP:LISTEN 2>/dev/null || true)"      # server web anterior dueño del 43917
[[ -n "$_web_pids" ]] && kill $_web_pids 2>/dev/null || true
# SPLIT-BRAIN (fix 2026-07-16): el reap de arriba solo mata al DUEÑO del 43917. Un `python -m server` HUÉRFANO
# (PPID=1, su run-livekit.sh ya murió) que YA NO es dueño del 43917 —porque un stack más nuevo se lo quedó—
# SOBREVIVE, pero su worker LiveKit EMBEBIDO sigue REGISTRADO en el 7880 → el dev server le despacha jobs de voz
# → el turno corre en el ZOMBI mientras el /events (SSE) del frontend cuelga del VIVO → "no cierra widgets", el
# cerebro no ve el canvas, la tarea muere. Reapamos TODO `python -m server` anterior (SIGTERM y, si lo ignora
# —visto en vivo—, SIGKILL); el que arrancamos abajo será el único con worker registrado.
for pid in $(pgrep -f "[Pp]ython -m server" 2>/dev/null || true); do kill "$pid" 2>/dev/null || true; done
sleep 0.5
for pid in $(pgrep -f "[Pp]ython -m server" 2>/dev/null || true); do kill -9 "$pid" 2>/dev/null || true; done
# espera a que el 7880 quede LIBRE (hasta ~6s) — si no, el probe de abajo re-detecta al zombi y volvemos al bug
for _ in $(seq 1 12); do nc -z 127.0.0.1 7880 2>/dev/null || break; sleep 0.5; done

# node-ip: NO lo fijamos (auto-sanación ante cambios de red — fix 2026-07-29). LiveKit/pion ENUMERA las interfaces
# VIVAS y reúne sus host-candidates ICE EN EL MOMENTO de cada PeerConnection nueva (no una vez al arrancar) → una
# conexión hecha DESPUÉS de cambiar de wifi/hotspot/casa-de-un-amigo anuncia sola la IP ACTUAL, sin reiniciar.
# FIJAR `--node-ip` al arranque (lo que hacíamos antes) DESACTIVABA justo ese auto-descubrimiento: LiveKit seguía
# anunciando la IP detectada al arrancar aunque ya no existiera en ninguna interfaz → 'wait_pc_connection timed out'
# en CADA cambio de red (incidente recurrente 2026-07-28: 3 caídas en un día al moverse entre redes).
# OJO — esto NO es el caso loopback: `--node-ip=127.0.0.1` SÍ falla (el agente embebido pion no reúne candidato
# loopback → no hay par ICE, confirmado por la comunidad LiveKit); por eso NO ponemos loopback, simplemente NO
# fijamos nada y dejamos el enumerado dinámico. La señalización sigue en `--bind 127.0.0.1` (privada, no LAN).
# Escape hatch power-user / entornos raros: `ZAELAR_LIVEKIT_NODE_IP=<ip>` restaura el viejo pin.
# PRODUCCIÓN (deploy real, no local): LiveKit Cloud o coturn/Cloudflare TURN → candidato relay con IP estable,
# independiente de la IP del nodo y del NAT del cliente. Ver zaelar-deploy.md. Detalle: research 2026-07-29.
LK_NODE_IP_ARG=""
if [[ -n "${ZAELAR_LIVEKIT_NODE_IP:-}" ]]; then
  LK_NODE_IP_ARG="--node-ip=${ZAELAR_LIVEKIT_NODE_IP}"
fi

# AUTO-INSTALL (self-contained first run, sin pasos manuales): si no hay binario nativo, intenta instalarlo solo
# ANTES de caer a Docker/error — macOS vía brew, Linux vía el instalador oficial. Silencioso si ya está.
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
# → voice muerta en TODO el sistema). Probe HTTP + add a settle margin before starting the web server.
for _ in $(seq 1 60); do curl -sf -m1 -o /dev/null "http://127.0.0.1:7880/" 2>/dev/null && break; nc -z 127.0.0.1 7880 2>/dev/null && break; sleep 0.5; done
sleep 2   # settle: let the agent service finish coming up so worker registration lands (evita la carrera de arranque)
echo "  ws://127.0.0.1:7880 (devkey/secret)"

echo "▶ servidor web zaelar (worker LiveKit EMBEBIDO, BRAIN=$BRAIN)…"
# El worker corre dentro de este proceso (ZAELAR_ENGINE=livekit → server lifespan monta AgentServer THREAD).
# No hay proceso worker aparte: así comparte el bus/observer-SSE, la memoria central, el loop orquestador y
# el buzón brain_notes con el cerebro «Colmena» (nucleo/).
( cd "$HERE" && ZAELAR_ENGINE=livekit exec "$PY" -m server ) & WEB_PID=$!

echo
echo "  ➜  abre  http://localhost:43917"
echo
wait
