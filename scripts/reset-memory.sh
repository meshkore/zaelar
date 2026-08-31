#!/usr/bin/env bash
#
# reset-memory.sh — deletes ONLY zaelar's HUMAN MEMORY and preserves EVERYTHING else (credentials, site auth,
# connector sessions, cookies, tokens). To start a natural test FROM SCRATCH ("¿cómo te llamas?", "¿dónde
# vives?") without having to re-authenticate Telegram/WhatsApp/Wallapop/cluster on every test.
#
# BOUNDARY (storage is separated by directory; see `.gitignore`):
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
# Usage:  bash scripts/reset-memory.sh [--dry-run] [--yes] [--keep-memory] [--wipe-credentials]
#   --dry-run          shows what it would delete/preserve, without touching anything.
#   --yes              skips the confirmation prompt (for `make reset-restart` and the frontend Reset dialog).
#   --keep-memory      does NOT delete memory.db/widget-states/episodic data (leaves MEMORY intact); it DOES clean
#                       observability (V2-063, Reset dialog with checkboxes: "Memoria" unchecked).
#   --wipe-credentials ALSO deletes connector credentials/auth/cookies (WhatsApp/Telegram/browser/
#                       search) — normally PRESERVED; this is the "Credenciales" checkbox checked.
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"
# Safety guard: do not run if we are not in the zaelar repository (prevents an rm in the wrong location).
[[ -f "$HERE/Makefile" && -d "$HERE/memory" && -d "$HERE/connectors" ]] || { echo "✗ no parece el repo de zaelar ($HERE)"; exit 1; }

DRY=0; YES=0; KEEP_MEMORY=0; WIPE_CREDS=0
for a in "$@"; do case "$a" in
  --dry-run) DRY=1;; --yes|-y) YES=1;;
  --keep-memory) KEEP_MEMORY=1;; --wipe-credentials) WIPE_CREDS=1;;
esac; done

# ── MEMORY components (V2-063: gated by --keep-memory) — EXPLICIT paths, never rm -rf on a parent ────
MEMORY_FILES=(
  "memory/_data/zaelar.db"
  "memory/_data/zaelar.db-wal"
  "memory/_data/zaelar.db-shm"
  "widgets/_data/mensajeria.json"
  "widgets/_data/whatsapp.json"
)
MEMORY_DIRS_CONTENTS=(
# episodic blobs (paste/drop) — part of memory
)
# widget content stores (calendar, messaging, timer…) — NOT the browser profile (cookies).
# `find` at EXACT depth 2 → widgets/_data/<id>/state.json; the browser profile is at depth 3+
# (widgets/_data/navegador/profile/…) → it NEVER reaches it. Collected without `mapfile` (macOS bash 3.2 does not include it).
WIDGET_STATES=()
while IFS= read -r _line; do [[ -n "$_line" ]] && WIDGET_STATES+=("$_line"); done \
  < <(find widgets/_data -mindepth 2 -maxdepth 2 -name 'state.json' 2>/dev/null || true)

# ── OBSERVABILIDAD (V2-063: SIEMPRE, es la base del diálogo de Reset — nunca gateada) ─────────────────────────
OBS_DIRS_CONTENTS=(
  ".meshkore/logs/sessions"        # event logs per session (to audit the zero-state test)
  ".meshkore/logs/voice"           # voice session folders (one per startup; opt-in recordings)
)

# ── CREDENTIALS/AUTH/COOKIES (V2-063: gated by --wipe-credentials; PRESERVED by default) ────────────
CRED_PATHS=(
  "connectors/whatsapp/_session"  "connectors/whatsapp/_data"
  "connectors/telegram/_session"
  "widgets/_data/navegador/profile"
  "memory/_data/search_browser"
)
# NEVER touched (even with --wipe-credentials): runtime config + zaelar's own credential store.
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

# 1) stop the server (the DB is open in WAL mode) — releases the lock and port for the restart.
if command -v lsof >/dev/null 2>&1; then
  PIDS="$(lsof -ti :43917 2>/dev/null || true)"
  [[ -n "$PIDS" ]] && { echo "▶ parando el server ($PIDS)…"; kill $PIDS 2>/dev/null || true; sleep 2; }
fi

# 2) delete observability (ALWAYS).
for d in "${OBS_DIRS_CONTENTS[@]}"; do [[ -d "$d" ]] && find "$d" -mindepth 1 -delete 2>/dev/null || true; done
: > .meshkore/logs/timeline-latest.jsonl 2>/dev/null || true

# 3) delete memory (only if NOT --keep-memory).
if [[ "$KEEP_MEMORY" != "1" ]]; then
  for f in "${MEMORY_FILES[@]}"; do [[ -e "$f" ]] && rm -f "$f"; done
  for d in "${MEMORY_DIRS_CONTENTS[@]}"; do [[ -d "$d" ]] && find "$d" -mindepth 1 -delete 2>/dev/null || true; done
  if [[ ${#WIDGET_STATES[@]} -gt 0 ]]; then for s in "${WIDGET_STATES[@]}"; do rm -f "$s"; done; fi
fi

# 4) delete credentials (only if --wipe-credentials).
if [[ "$WIPE_CREDS" == "1" ]]; then
  for c in "${CRED_PATHS[@]}"; do [[ -e "$c" ]] && rm -rf "$c"; done
fi

# BLANK DESKTOP after the wipeout: open widgets are persisted in the BROWSER's localStorage
# (hb_desktop), which a server deletion does NOT reach → they would reappear on reload. We bump a WIPE EPOCH that
# the server serves (/api/desktop/epoch); on startup, if the frontend sees a new epoch, it clears its local desktop
# → blank session as if freshly installed. (This file is NOT deleted during the wipe; only its value changes.)
date +%s > .meshkore/logs/desktop-epoch 2>/dev/null || true

echo "✓ observabilidad borrada"\
"$([[ "$KEEP_MEMORY" != "1" ]] && echo " + memoria humana borrada")"\
"$([[ "$WIPE_CREDS" == "1" ]] && echo " + credenciales/auth/cookies borradas")"\
". Escritorio en blanco al recargar. En el próximo arranque, zaelar empieza"\
"$([[ "$KEEP_MEMORY" != "1" ]] && echo " de cero" || echo " con tu memoria intacta")."
