#!/usr/bin/env bash
# memory_cron_tick.sh — ONE tick of the memory test→fix cron (V2-050, hermano de tests/voice/e2e/agent/cron_tick.sh).
# Mitad DETERMINISTA del bucle (el agente Claude hace la mitad de juicio/arreglo, leyendo el VERDICT):
#   1) REGRESIÓN rápida: pytest de precisión de memoria (gates V2-033/V2-050 + unit + integration). BD aislada,
#      SIN servidor, SIN GPU — es la red que garantiza que un fix nuevo no rompe lo anterior.
#   2) EVAL PROFUNDO rotatorio: una tanda del bot de memoria (taxonomía A-X, camino REAL con el CORAZÓN LLM local),
#      cursor round-robin persistido → cada tick avanza por el corpus sin repetir a ciegas.
#   3) VERDICT compacto que el agente parsea para decidir PASS / FIX.
# NUNCA toca el perfil real (el bot usa ZAELAR_DB aislado). Exit 0 siempre (el agente lee la salida).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PY="$HERE/.venv/bin/python"
RUNS="$HERE/tests/memory/e2e/bot/runs"; mkdir -p "$RUNS"
CURSOR="$RUNS/.cron-cursor"
LOG="$RUNS/cron.log"

say(){ echo "[mem_cron $(date +%H:%M:%S)] $*"; }
cd "$HERE" || { echo "VERDICT status=INFRA phase=cd reason=no_repo"; exit 0; }

# ── 1) REGRESIÓN determinista (pytest) ───────────────────────────────────────────────────────────────────────
PYT_OUT=$("$PY" -m pytest tests/memory/integration/test_write_precision_v2050.py \
                          tests/memory/integration/test_write_precision_v2033.py \
                          tests/memory/integration/test_memory_agent.py tests/memory/unit/test_compose_state.py \
                          -q --no-header 2>&1 | tail -3)
echo "$PYT_OUT" >> "$LOG"
if echo "$PYT_OUT" | grep -qE '[0-9]+ failed'; then
  PYT_STATUS=FAIL
else
  PYT_STATUS=PASS
fi
PYT_LINE=$(echo "$PYT_OUT" | grep -oE '[0-9]+ (passed|failed)(, [0-9]+ (passed|failed|skipped))*' | tail -1)

# ── 2) EVAL PROFUNDO: una tanda del bot de memoria (real, LLM local) ─────────────────────────────────────────
# Requiere Ollama (CORAZÓN). Si no está, saltamos el eval profundo pero la regresión ya corrió.
# REPLAY FRESCO de las primeras N de un corpus ROTATORIO (v1/v2/v3) — cada tick varía el corpus (cursor) y replaya
# desde 0 (el corpus es una conversación lineal; un tramo del medio sin contexto no tiene sentido → --fresh).
BOT_STATUS=SKIP; BOT_LINE="ollama_down"
if curl -sf -m 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  N=${MEM_CRON_BATCH:-10}
  MAXD=${MEM_CRON_MAX:-120}         # profundidad máx por tick — subido 40→120 (2 ciclos planos en verde: la
                                    # ventana debe seguir AVANZANDO a terreno nuevo, casos 40+ nunca vistos por el
                                    # loop; ticks profundos corren en background, sin bloquear el intervalo)
  CORPORA=(v3 v2 v1)
  DEPTHF="$RUNS/.cron-depth"
  ci=0; [ -f "$CURSOR" ] && ci=$(cat "$CURSOR" 2>/dev/null || echo 0)
  [[ "$ci" =~ ^[0-9]+$ ]] || ci=0
  d=0; [ -f "$DEPTHF" ] && d=$(cat "$DEPTHF" 2>/dev/null || echo 0)
  [[ "$d" =~ ^[0-9]+$ ]] || d=0
  CORPUS="${CORPORA[$(( ci % ${#CORPORA[@]} ))]}"
  # VENTANA CRECIENTE: cada tick explora MÁS profundo [0, HI) — el corpus es conversación lineal, así que se
  # replaya desde 0 (--fresh) hasta HI. Al tocar el tope, reinicia profundidad y ROTA de corpus → cobertura nueva
  # sin re-probar eternamente las mismas 10 (aviso de los 4 ticks planos).
  HI=$(( N * (d + 1) ))
  [ "$HI" -ge "$MAXD" ] && { HI=$MAXD; echo 0 > "$DEPTHF"; echo $(( (ci + 1) % ${#CORPORA[@]} )) > "$CURSOR"; } \
                        || echo $(( d + 1 )) > "$DEPTHF"
  say "bot corpus=$CORPUS (fresh, range 0..$HI)"
  # tail generoso: el runner imprime "=== TANDA" ARRIBA (antes de ~HI líneas de resultados) y
  # "Progreso acumulado" ABAJO; con la ventana creciendo hasta MAXD(120) un tail corto se comía la
  # línea de resumen → FAILN caía a 0 → el bot marcaba PASS aunque hubiera fallos (detector CIEGO,
  # 2026-07-17). Fuente de verdad = "Progreso acumulado" (SIEMPRE al final, sobrevive al tail; con
  # --fresh refleja SOLO esta corrida); fallback a "=== TANDA".
  BOT_OUT=$(ZAELAR_DB="$HERE/memory/_data/zaelar.membot.db" MEM_PROCESSOR=1 \
            "$PY" -m tests.memory.e2e.bot.runner --fresh --range 0 "$HI" --corpus "$CORPUS" 2>&1 | tail -$(( MAXD + 40 )))
  echo "$BOT_OUT" >> "$LOG"
  BOT_LINE=$(echo "$BOT_OUT" | grep -E 'Progreso acumulado' | tail -1)
  [ -z "$BOT_LINE" ] && BOT_LINE=$(echo "$BOT_OUT" | grep -E '=== TANDA' | tail -1)
  if [ -z "$BOT_LINE" ]; then
    # NO hay línea de resumen → el runner reventó (no es un fallo de gate de memoria). INFRA, no FIX.
    BOT_STATUS=INFRA; BOT_LINE="runner_sin_resumen (crash?)"
  else
    FAILN=$(echo "$BOT_LINE" | grep -oE '[0-9]+ fallos' | grep -oE '[0-9]+' | head -1)
    [ -z "$FAILN" ] && FAILN=0
    if [ "$FAILN" -gt 0 ]; then BOT_STATUS=FAIL; else BOT_STATUS=PASS; fi
  fi
  # líneas de los casos FALLADOS (para que el agente sepa QUÉ arreglar)
  echo "$BOT_OUT" | grep -E '^\s*❌' | head -8 > "$RUNS/.last-fails"
fi

# ── 3) VERDICT ───────────────────────────────────────────────────────────────────────────────────────────────
STATUS=PASS
[ "$PYT_STATUS" = FAIL ] && STATUS=FIX
[ "$BOT_STATUS" = FAIL ] && STATUS=FIX
echo "VERDICT status=$STATUS pytest=$PYT_STATUS ($PYT_LINE) bot=$BOT_STATUS"
echo "BOT $BOT_LINE"
if [ -s "$RUNS/.last-fails" ] && [ "$BOT_STATUS" = FAIL ]; then
  say "casos fallados:"; sed 's/^/FAIL_CASE /' "$RUNS/.last-fails"
fi
exit 0
