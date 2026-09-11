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
#                       search) AND `config/connectors.json`, which is where the email app password, the
#                       Telegram api_id/hash and the per-connector flags actually live — the dialog has
#                       always PROMISED that checkbox deletes widget credentials and that file was in
#                       KEEP_ALWAYS, so half of them survived (measured 2026-09-11).
#   --factory          "as if for the FIRST time" (V2-670): strips settings.json down to the INSTALLATION's
#                       own setup (which paid STT/TTS provider, the profile) and drops the AGENT's side —
#                       `stt_language` above all, which is the gate `i18n.init.detect.should_detect()` reads
#                       to decide whether the first-run LANGUAGE CEREMONY fires. Also drops the install id,
#                       the spoken style rules, the library layout and the generated i18n packs. The split
#                       lives in `config/settings.py` (INSTALL_KEYS/AGENT_KEYS) with a ratchet, not here.
#   --wipe-files       ALSO deletes the agent's FILE SYSTEM: `library/` (downloads, documents, images,
#                       audio). These are real files the operator asked for, so they are their own checkbox
#                       and never ride along with anything else.
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"
# Safety guard: do not run if we are not in the zaelar repository (prevents an rm in the wrong location).
[[ -f "$HERE/Makefile" && -d "$HERE/memory" && -d "$HERE/connectors" ]] || { echo "✗ no parece el repo de zaelar ($HERE)"; exit 1; }

DRY=0; YES=0; KEEP_MEMORY=0; WIPE_CREDS=0; FACTORY=0; WIPE_FILES=0
for a in "$@"; do case "$a" in
  --dry-run) DRY=1;; --yes|-y) YES=1;;
  --keep-memory) KEEP_MEMORY=1;; --wipe-credentials) WIPE_CREDS=1;;
  --factory) FACTORY=1;; --wipe-files) WIPE_FILES=1;;
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
  # Episodic blobs (paste/drop). They ARE memory's payload — `memory.write_episode` stores the binary here and
  # the row that points at it in zaelar.db — so they have to die WITH the database or you are left with either
  # orphan files or rows pointing at nothing. This array was EMPTY while the comment above it already said
  # «part of memory»: measured 2026-09-11 with 37 surviving files (contracts, CVs) after a full reset.
  "memory/_data/episodic"
  # Per-errand results instances (`widgets/_data/results--<id>/`) and the generation journal: pure content,
  # accumulated one per errand — 60+ of them on the operator's machine, none of them reachable after a wipe.
)
# widget content stores (calendar, messaging, timer…) — NOT the browser profile (cookies).
# `find` at EXACT depth 2 → widgets/_data/<id>/state.json; the browser profile is at depth 3+
# (widgets/_data/navegador/profile/…) → it NEVER reaches it. Collected without `mapfile` (macOS bash 3.2 does not include it).
# Broadened from `state.json` to `*.json` (V2-670): the browser widget also keeps `ws_<site>.json` and
# `informe.json` at that depth and they were surviving every wipe. Depth is still EXACTLY 2, so the cookie
# profile (widgets/_data/navegador/profile/…, depth 3+) is still never reached.
WIDGET_STATES=()
while IFS= read -r _line; do [[ -n "$_line" ]] && WIDGET_STATES+=("$_line"); done \
  < <(find widgets/_data -mindepth 2 -maxdepth 2 -name '*.json' 2>/dev/null || true)
WIDGET_STATES+=("widgets/_data/_jobs.json")
RESULTS_DIRS=()
while IFS= read -r _line; do [[ -n "$_line" ]] && RESULTS_DIRS+=("$_line"); done \
  < <(find widgets/_data -mindepth 1 -maxdepth 1 -type d -name 'results--*' 2>/dev/null || true)

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
  "config/connectors.json"        # email app password + telegram api_id/hash + per-connector flags
)

# ── FACTORY (V2-670: gated by --factory) — the AGENT's identity, not the machine's setup ──────────────
FACTORY_PATHS=(
  "config/identity.json"   # the installation's own UUID; boot regenerates it and logs it (V2-090)
  "config/style.json"      # spoken style rules (V2-633)
  "config/library.json"    # per-install library layout (V2-638)
)
FACTORY_DIRS_CONTENTS=(
  "i18n/generated"         # alias/filler packs generated at a previous onboarding (V2-101)
)

# ── THE AGENT'S FILES (V2-670: gated by --wipe-files) ────────────────────────────────────────────────
FILE_DIRS_CONTENTS=(
  "library/downloads" "library/documents" "library/images" "library/audio"
)
# NEVER touched (even with --wipe-credentials): runtime config + zaelar's own credential store.
# NEVER touched by ANY flag: the machine's own keys and the model routing. `config/settings.json` is no
# longer here — `--factory` rewrites it SURGICALLY (see config/settings.py::factory_reset), because deleting
# it whole would swap the paid STT/TTS provider underneath a test that is itself spoken.
KEEP_ALWAYS=(
  "config/v2.json" "config/meshkore.json" ".env" ".meshkore/credentials"
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
  if [[ ${#WIDGET_STATES[@]} -gt 0 ]]; then for s in "${WIDGET_STATES[@]}"; do [[ -e "$s" ]] && echo "  · $s"; done; fi
  [[ ${#RESULTS_DIRS[@]} -gt 0 ]] && echo "  · ${#RESULTS_DIRS[@]} carpetas widgets/_data/results--* (instancias de hojas)"
fi
if [[ "$WIPE_CREDS" == "1" ]]; then
  echo "BORRA — credenciales/auth/cookies (checkbox 'Credenciales de widgets'):"
  for c in "${CRED_PATHS[@]}"; do [[ -e "$c" ]] && echo "  · $c"; done
else
  echo "CONSERVA — credenciales/auth/cookies:"
  for c in "${CRED_PATHS[@]}"; do [[ -e "$c" ]] && echo "  ✓ $c" || echo "  · $c (no existe)"; done
fi
if [[ "$FACTORY" == "1" ]]; then
  echo "BORRA — identidad del AGENTE (checkbox 'empezar de cero, como la primera vez'):"
  echo "  · config/settings.json → se deja SOLO el montaje de la instalación (proveedor STT/TTS, perfil)"
  echo "    y se va el idioma, la voz, el modo de atención, el wizard y el fondo de escritorio"
  for f in "${FACTORY_PATHS[@]}"; do [[ -e "$f" ]] && echo "  · $f"; done
  for d in "${FACTORY_DIRS_CONTENTS[@]}"; do [[ -d "$d" ]] && echo "  · $d/* (contenido)"; done
else
  echo "CONSERVA — identidad del agente (idioma, voz, perfil, wizard):"
  echo "  ✓ config/settings.json"
fi
if [[ "$WIPE_FILES" == "1" ]]; then
  echo "BORRA — los FICHEROS del agente (checkbox 'borrar los ficheros'):"
  for d in "${FILE_DIRS_CONTENTS[@]}"; do [[ -d "$d" ]] && echo "  · $d/* ($(du -sh "$d" 2>/dev/null | cut -f1))"; done
else
  echo "CONSERVA — los ficheros del agente:"
  for d in "${FILE_DIRS_CONTENTS[@]}"; do [[ -d "$d" ]] && echo "  ✓ $d ($(du -sh "$d" 2>/dev/null | cut -f1))"; done
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
  if [[ ${#RESULTS_DIRS[@]} -gt 0 ]]; then for d in "${RESULTS_DIRS[@]}"; do rm -rf "$d"; done; fi
fi

# 4) delete credentials (only if --wipe-credentials).
if [[ "$WIPE_CREDS" == "1" ]]; then
  for c in "${CRED_PATHS[@]}"; do [[ -e "$c" ]] && rm -rf "$c"; done
fi

# 5) FACTORY (only if --factory): settings.json is rewritten SURGICALLY by the module that owns the split,
# so bash never encodes which knob belongs to whom — one source, with a ratchet over it.
if [[ "$FACTORY" == "1" ]]; then
  PY_BIN="./.venv/bin/python"; [[ -x "$PY_BIN" ]] || PY_BIN="$(command -v python3 || true)"
  if [[ -n "$PY_BIN" ]]; then
    "$PY_BIN" -c "from config.settings import factory_reset; r = factory_reset(); print('  settings.json → conserva', r['kept'], '· borra', r['dropped'])" \
      || echo "  ⚠ no pude reescribir settings.json (sigo con el resto)"
  else
    echo "  ⚠ sin python disponible: settings.json NO se ha tocado"
  fi
  for f in "${FACTORY_PATHS[@]}"; do [[ -e "$f" ]] && rm -f "$f"; done
  for d in "${FACTORY_DIRS_CONTENTS[@]}"; do [[ -d "$d" ]] && find "$d" -mindepth 1 -delete 2>/dev/null || true; done
fi

# 6) THE AGENT'S FILES (only if --wipe-files).
if [[ "$WIPE_FILES" == "1" ]]; then
  for d in "${FILE_DIRS_CONTENTS[@]}"; do [[ -d "$d" ]] && find "$d" -mindepth 1 -delete 2>/dev/null || true; done
fi

# BLANK DESKTOP after the wipeout: open widgets are persisted in the BROWSER's localStorage
# (hb_desktop), which a server deletion does NOT reach → they would reappear on reload. We bump a WIPE EPOCH that
# the server serves (/api/desktop/epoch); on startup, if the frontend sees a new epoch, it clears its local desktop
# → blank session as if freshly installed. (This file is NOT deleted during the wipe; only its value changes.)
date +%s > .meshkore/logs/desktop-epoch 2>/dev/null || true

echo "✓ observabilidad borrada"\
"$([[ "$KEEP_MEMORY" != "1" ]] && echo " + memoria humana borrada")"\
"$([[ "$WIPE_CREDS" == "1" ]] && echo " + credenciales/auth/cookies borradas")"\
"$([[ "$FACTORY" == "1" ]] && echo " + identidad del agente borrada (arranca preguntando el idioma)")"\
"$([[ "$WIPE_FILES" == "1" ]] && echo " + ficheros del agente borrados")"\
". Escritorio en blanco al recargar. En el próximo arranque, zaelar empieza"\
"$([[ "$KEEP_MEMORY" != "1" ]] && echo " de cero" || echo " con tu memoria intacta")."
