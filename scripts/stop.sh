#!/usr/bin/env bash
#
# stop.sh — PARA todo lo que arranca zaelar y LIBERA la batería. Detiene el server web (puerto 43917), el
# servidor LiveKit nativo, los lanzadores, los workers del SlowBrain (Claude Code headless + subprocesos
# nucleo.*) y DESCARGA los modelos de Ollama de la GPU/RAM (se quedan calientes por `keep_alive` y drenan
# batería aunque no haya nadie hablando). NO toca credenciales, memoria ni datos — solo procesos.
#
# Vuelve a arrancar con `make run`.
#
# Uso:  bash scripts/stop.sh
set -uo pipefail   # sin -e: un pkill sin match (exit 1) no debe abortar el script

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f "$HERE/Makefile" && -d "$HERE/nucleo" ]] || { echo "✗ no parece el repo de zaelar ($HERE)"; exit 1; }

echo "▶ parando zaelar…"

# 1) server web (puerto 43917) — TERM y, si persiste, KILL.
P="$(lsof -ti :43917 2>/dev/null || true)"
if [[ -n "$P" ]]; then kill $P 2>/dev/null || true; sleep 2; fi
P="$(lsof -ti :43917 2>/dev/null || true)"
[[ -n "$P" ]] && kill -9 $P 2>/dev/null || true

# 2) servidor LiveKit nativo + lanzadores.
pkill -f "livekit-server --dev" 2>/dev/null || true
pkill -f "run-livekit.sh"       2>/dev/null || true

# 3) workers del SlowBrain: subprocesos nucleo.* y el Claude Code headless que los orquesta. Se identifican por
#    su firma zaelar (`nucleo.worker_bridge`/`nucleo.nav_cli`/`nucleo.mem_cli`/`nucleo.agent_report`) → NUNCA
#    matamos otras sesiones `claude` del operador (esta incluida): solo las que llevan esas tools en la línea.
pkill -f "nucleo.worker_bridge" 2>/dev/null || true
pkill -f "nucleo.nav_cli"       2>/dev/null || true
pkill -f "nucleo.agent_report"  2>/dev/null || true
pkill -f "claude.*nucleo.mem_cli"      2>/dev/null || true
pkill -f "claude.*nucleo.worker_bridge" 2>/dev/null || true

# 4) Chromium de búsqueda / navegador lanzado por zaelar (perfil propio, aislado del Chrome del operador).
pkill -f "search_browser" 2>/dev/null || true
pkill -f "widgets/_data/navegador/profile" 2>/dev/null || true

# 5) DESCARGAR los modelos de Ollama cargados (libera GPU/RAM → batería). No para el servicio ollama; solo
#    descarga los modelos residentes (keep_alive). Genérico: descarga TODO lo que `ollama ps` liste.
if command -v ollama >/dev/null 2>&1; then
  ollama ps 2>/dev/null | awk 'NR>1 && $1!="" {print $1}' | while IFS= read -r m; do
    [[ -n "$m" ]] && { ollama stop "$m" 2>/dev/null && echo "  ✗ ollama: descargado $m"; }
  done
fi

sleep 1
LEFT="$(lsof -ti :43917 2>/dev/null || true)"
LK="$(pgrep -f 'livekit-server' 2>/dev/null || true)"
OLL="$(ollama ps 2>/dev/null | awk 'NR>1 && $1!="" {print $1}' | tr '\n' ' ' || true)"
echo "── estado ──"
echo "  puerto 43917: $([[ -z "$LEFT" ]] && echo libre || echo "AÚN $LEFT")"
echo "  livekit:     $([[ -z "$LK" ]] && echo parado || echo "AÚN $LK")"
echo "  ollama:      $([[ -z "$OLL" ]] && echo "sin modelos cargados" || echo "AÚN: $OLL")"
echo "✓ zaelar parado. Arranca de nuevo con: make run"
