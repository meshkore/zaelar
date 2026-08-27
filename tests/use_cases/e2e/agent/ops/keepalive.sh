#!/bin/zsh
# «El plató no para» sin launchd (V2-417).
#
# POR QUÉ NO LAUNCHD, escrito aquí para que nadie lo vuelva a intentar a ciegas: el repo vive bajo
# `~/Documents`, y macOS (TCC) le niega a un agente de launchd la lectura de esa carpeta salvo que el
# operador conceda Acceso Total al Disco a mano. Medido el 2026-08-28: el agente arrancó y murió con
# `127 · can't open input file` sobre un fichero que existe y es ejecutable. `crontab` topa con lo mismo.
# Así que el guardián es este bucle, arrancado desacoplado de cualquier sesión.
#
# QUÉ CUBRE: que el supervisor muera (excepción, OOM, un `kill`, un plató que se lleva el proceso por
# delante). Vuelve a levantarlo tras `ESPERA_S`.
# QUÉ NO CUBRE: un REINICIO de la máquina. Para eso hace falta el plist de `ops/` y el permiso de disco
# — está escrito y probado hasta donde TCC deja; es un gesto del operador, no algo que se pueda automatizar.
#
# UNO Y SOLO UNO: hay un navegador por plató, y dos supervisores midiendo a la vez se pelean por la misma
# pestaña y las dos rondas salen mal. El candado es un fichero con el PID, comprobado de verdad contra el
# proceso — un fichero suelto no basta, porque un guardián matado deja el suyo detrás para siempre.
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
