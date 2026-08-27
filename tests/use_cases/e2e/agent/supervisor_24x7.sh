#!/bin/zsh
# El plató NO PARA — envoltorio de arranque para el supervisor (V2-417).
#
# El supervisor ya es un bucle infinito que no muere por una ronda y se recarga solo cuando cambia su
# propio código. Lo que NO sabe hacer es volver a existir: si el proceso muere (una actualización, un
# `killall python`, un reinicio de la máquina) no hay nadie que lo levante. Eso lo pone launchd con
# `KeepAlive`; este script es lo que launchd arranca, y su único trabajo es dejar el mundo en condiciones
# ANTES de entrar al bucle.
#
# Levantar los platós aquí y no dentro del supervisor es deliberado: tras un reinicio no hay ningún plató
# vivo, y un supervisor que arranca contra puertos muertos no falla — mide, y escribe una fila INFRA por
# cada escenario de la rotación hasta que alguien mira. Un bucle que produce basura a toda velocidad es
# peor que uno parado, porque el parado se nota.
set -u
cd "$(dirname "$0")/../../../.." || exit 1        # → engine/

LOGS="tests/runs/use_cases/supervisor"
mkdir -p "$LOGS"

echo "[$(date '+%F %T')] arrancando · HEAD $(git rev-parse --short HEAD 2>/dev/null)" >> "$LOGS/arranques.log"

# Los platós, idempotente: `up` sobre uno ya vivo lo respeta (conserva puerto, memoria y perfil).
./.venv/bin/python -m tests.use_cases.lab up all >> "$LOGS/arranques.log" 2>&1

# ZAELAR_UC_CAFFEINATE=0 para dejar que el Mac se duerma. Por defecto se impide el sueño POR INACTIVIDAD
# (`caffeinate -i`), que es lo único que separa «corriendo 24 h» de «corriendo hasta que te vas a cenar».
# No impide el sueño al cerrar la tapa: eso sigue siendo decisión física del operador.
if [[ "${ZAELAR_UC_CAFFEINATE:-1}" == "1" ]] && command -v caffeinate >/dev/null; then
  exec caffeinate -i ./.venv/bin/python -m tests.use_cases.e2e.agent.supervisor
fi
exec ./.venv/bin/python -m tests.use_cases.e2e.agent.supervisor
