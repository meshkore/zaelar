#!/usr/bin/env bash
#
# reset-memory.sh — borra SOLO la MEMORIA HUMANA de zaelar y conserva TODO lo demás (credenciales, auth de sitios,
# sesiones de conectores, cookies, tokens). Para empezar un test natural DESDE CERO ("¿cómo te llamas?", "¿dónde
# vives?") sin tener que re-autenticar Telegram/WhatsApp/Wallapop/cluster en cada prueba.
#
# FRONTERA (el storage está separado por directorio; ver `.gitignore`):
#   MEMORIA HUMANA (se BORRA)          | CREDENCIALES / AUTH / COOKIES (se CONSERVA)
#   -----------------------------------|-------------------------------------------------
#   memory/_data/zaelar.db (+wal/shm)  | connectors/whatsapp/_session  (claves Baileys)
#   memory/_data/episodic/             | connectors/whatsapp/_data
#   widgets/_data/mensajeria/          | connectors/telegram/_session/zaelar.session
#   widgets/_data/<widget>/state.json  | widgets/_data/navegador/profile  (cookies Wallapop/Google)
#   widgets/_data/*.json (msg stores)  | memory/_data/search_browser  (perfil Chromium de búsqueda)
#                                      | config/*.json  (settings/connectors/v2/meshkore = tokens WS)
#                                      | .env · .meshkore/credentials/
#
# Uso:  bash scripts/reset-memory.sh [--dry-run] [--yes] [--keep-memory] [--wipe-credentials]
#   --dry-run          muestra qué borraría/conservaría, sin tocar nada.
#   --yes              no pregunta confirmación (para `make reset-restart` y el diálogo de Reset del frontend).
#   --keep-memory      NO borra memory.db/widget-states/episódica (deja la MEMORIA intacta); SÍ limpia
#                       observabilidad (V2-063, diálogo de Reset con checkboxes: "Memoria" desmarcada).
#   --wipe-credentials ADEMÁS borra credenciales/auth/cookies de conectores (WhatsApp/Telegram/navegador/
#                       búsqueda) — normalmente se CONSERVAN; esto es el checkbox "Credenciales" marcado.
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"
# Guard de seguridad: no ejecutar si no estamos en el repo de zaelar (evita un rm en el sitio equivocado).
[[ -f "$HERE/Makefile" && -d "$HERE/memory" && -d "$HERE/connectors" ]] || { echo "✗ no parece el repo de zaelar ($HERE)"; exit 1; }

DRY=0; YES=0; KEEP_MEMORY=0; WIPE_CREDS=0
for a in "$@"; do case "$a" in
  --dry-run) DRY=1;; --yes|-y) YES=1;;
  --keep-memory) KEEP_MEMORY=1;; --wipe-credentials) WIPE_CREDS=1;;
esac; done

# ── piezas de MEMORIA (V2-063: gateadas por --keep-memory) — rutas EXPLÍCITAS, nunca rm -rf sobre un padre ────
MEMORY_FILES=(
  "memory/_data/zaelar.db"
  "memory/_data/zaelar.db-wal"
  "memory/_data/zaelar.db-shm"
  "widgets/_data/mensajeria.json"
  "widgets/_data/whatsapp.json"
)
MEMORY_DIRS_CONTENTS=(
  "memory/_data/episodic"          # blobs episódicos (paste/drop) — parte de la memoria
)
# stores de contenido de widgets (agenda, mensajería, timer…) — NO el perfil del navegador (cookies).
# `find` a profundidad EXACTA 2 → widgets/_data/<id>/state.json; el perfil del navegador está a profundidad 3+
# (widgets/_data/navegador/profile/…) → NUNCA lo alcanza. Recogido sin `mapfile` (bash 3.2 de macOS no lo trae).
WIDGET_STATES=()
while IFS= read -r _line; do [[ -n "$_line" ]] && WIDGET_STATES+=("$_line"); done \
  < <(find widgets/_data -mindepth 2 -maxdepth 2 -name 'state.json' 2>/dev/null || true)

# ── OBSERVABILIDAD (V2-063: SIEMPRE, es la base del diálogo de Reset — nunca gateada) ─────────────────────────
OBS_DIRS_CONTENTS=(
  ".meshkore/logs/sessions"        # logs de evento por sesión (para auditar el test a cero)
  ".meshkore/logs/voice"           # carpetas de sesión de voz (una por arranque; grabaciones opt-in)
)

# ── CREDENCIALES/AUTH/COOKIES (V2-063: gateadas por --wipe-credentials; por defecto se CONSERVAN) ────────────
CRED_PATHS=(
  "connectors/whatsapp/_session"  "connectors/whatsapp/_data"
  "connectors/telegram/_session"
  "widgets/_data/navegador/profile"
  "memory/_data/search_browser"
)
# NUNCA se tocan (ni con --wipe-credentials): config runtime + el credential store del propio zaelar.
KEEP_ALWAYS=(
  "config/settings.json" "config/connectors.json" "config/v2.json" "config/meshkore.json"
  ".env" ".meshkore/credentials"
)

echo "── RESET $([[ "$DRY" == "1" ]] && echo "(DRY-RUN)" || echo "(EJECUTANDO)") ──"
echo "BORRA — observabilidad (siempre):"
for d in "${OBS_DIRS_CONTENTS[@]}"; do [[ -d "$d" ]] && echo "  · $d/* (contenido)"; done
echo "  · .meshkore/logs/timeline-latest.jsonl (vaciado)"
if [[ "$KEEP_MEMORY" == "1" ]]; then
  echo "CONSERVA — memoria (state/corto/largo):"
  echo "  ✓ memory/_data/zaelar.db · widgets/_data/*/state.json"
else
  echo "BORRA — memoria (state/corto/largo, checkbox 'Memoria'):"
  for f in "${MEMORY_FILES[@]}"; do [[ -e "$f" ]] && echo "  · $f"; done
  for d in "${MEMORY_DIRS_CONTENTS[@]}"; do [[ -d "$d" ]] && echo "  · $d/* (contenido)"; done
  if [[ ${#WIDGET_STATES[@]} -gt 0 ]]; then for s in "${WIDGET_STATES[@]}"; do echo "  · $s"; done; fi
fi
if [[ "$WIPE_CREDS" == "1" ]]; then
  echo "BORRA — credenciales/auth/cookies (checkbox 'Credenciales de widgets'):"
  for c in "${CRED_PATHS[@]}"; do [[ -e "$c" ]] && echo "  · $c"; done
else
  echo "CONSERVA — credenciales/auth/cookies:"
  for c in "${CRED_PATHS[@]}"; do [[ -e "$c" ]] && echo "  ✓ $c" || echo "  · $c (no existe)"; done
fi
echo "NUNCA se toca:"
for k in "${KEEP_ALWAYS[@]}"; do [[ -e "$k" ]] && echo "  ✓ $k" || echo "  · $k (no existe)"; done

if [[ "$DRY" == "1" ]]; then echo "(dry-run: nada tocado)"; exit 0; fi

if [[ "$YES" != "1" ]]; then
  read -r -p "¿Seguro? Esto borra lo de arriba (irreversible). Escribe 'si': " ans
  [[ "$ans" == "si" || "$ans" == "sí" ]] || { echo "cancelado"; exit 0; }
fi

# 1) parar el server (la BD está abierta en WAL) — libera el lock y el puerto para el restart.
if command -v lsof >/dev/null 2>&1; then
  PIDS="$(lsof -ti :43917 2>/dev/null || true)"
  [[ -n "$PIDS" ]] && { echo "▶ parando el server ($PIDS)…"; kill $PIDS 2>/dev/null || true; sleep 2; }
fi

# 2) borrar observabilidad (SIEMPRE).
for d in "${OBS_DIRS_CONTENTS[@]}"; do [[ -d "$d" ]] && find "$d" -mindepth 1 -delete 2>/dev/null || true; done
: > .meshkore/logs/timeline-latest.jsonl 2>/dev/null || true

# 3) borrar memoria (solo si NO --keep-memory).
if [[ "$KEEP_MEMORY" != "1" ]]; then
  for f in "${MEMORY_FILES[@]}"; do [[ -e "$f" ]] && rm -f "$f"; done
  for d in "${MEMORY_DIRS_CONTENTS[@]}"; do [[ -d "$d" ]] && find "$d" -mindepth 1 -delete 2>/dev/null || true; done
  if [[ ${#WIDGET_STATES[@]} -gt 0 ]]; then for s in "${WIDGET_STATES[@]}"; do rm -f "$s"; done; fi
fi

# 4) borrar credenciales (solo si --wipe-credentials).
if [[ "$WIPE_CREDS" == "1" ]]; then
  for c in "${CRED_PATHS[@]}"; do [[ -e "$c" ]] && rm -rf "$c"; done
fi

# ESCRITORIO EN BLANCO tras el wipeout: los widgets abiertos se persisten en el localStorage del NAVEGADOR
# (hb_desktop), que un borrado de servidor NO alcanza → reaparecerían al recargar. Bumpeamos una ÉPOCA DE WIPE que
# el server sirve (/api/desktop/epoch); el frontend, al arrancar, si ve una época nueva, vacía su escritorio local
# → sesión en blanco como recién instalado. (Este fichero NO se borra en el wipe; solo cambia su valor.)
date +%s > .meshkore/logs/desktop-epoch 2>/dev/null || true

echo "✓ observabilidad borrada"\
"$([[ "$KEEP_MEMORY" != "1" ]] && echo " + memoria humana borrada")"\
"$([[ "$WIPE_CREDS" == "1" ]] && echo " + credenciales/auth/cookies borradas")"\
". Escritorio en blanco al recargar. En el próximo arranque, zaelar empieza"\
"$([[ "$KEEP_MEMORY" != "1" ]] && echo " de cero" || echo " con tu memoria intacta")."
