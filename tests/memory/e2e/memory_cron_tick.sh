#!/usr/bin/env bash
# memory_cron_tick.sh — ONE tick of the memory test→fix cron (V2-050, sibling of tests/voice/e2e/agent/cron_tick.sh).
# DETERMINISTIC half of the loop (the Claude agent handles the judgment/fix half, reading the VERDICT):
#   1) Quick REGRESSION: memory-precision pytest (V2-033/V2-050 gates + unit + integration). Isolated DB,
#      NO server, NO GPU — the safety net ensuring that a new fix does not break what came before.
#   2) Rotating DEEP EVAL: one batch from the memory bot (A-X taxonomy, REAL path with the local LLM CORE),
#      persisted round-robin cursor → each tick advances through the corpus without blindly repeating.
#   3) Compact VERDICT that the agent parses to decide PASS / FIX.
# NEVER touches the real profile (the bot uses an isolated ZAELAR_DB). Always exits 0 (the agent reads the output).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PY="$HERE/.venv/bin/python"
RUNS="$HERE/tests/memory/e2e/bot/runs"; mkdir -p "$RUNS"
CURSOR="$RUNS/.cron-cursor"
LOG="$RUNS/cron.log"

say(){ echo "[mem_cron $(date +%H:%M:%S)] $*"; }
cd "$HERE" || { echo "VERDICT status=INFRA phase=cd reason=no_repo"; exit 0; }

# ── 1) Deterministic REGRESSION (pytest) ───────────────────────────────────────────────────────────────────────
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

# ── 2) DEEP EVAL: one batch from the memory bot (real, local LLM) ─────────────────────────────────────────
# Requires Ollama (CORE). If it is unavailable, skip the deep eval, but the regression has already run.
# FRESH REPLAY of the first N items from a ROTATING corpus (v1/v2/v3) — each tick varies the corpus (cursor) and replays
# from 0 (the corpus is a linear conversation; a middle segment without context makes no sense → --fresh).
BOT_STATUS=SKIP; BOT_LINE="ollama_down"
if curl -sf -m 3 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  N=${MEM_CRON_BATCH:-10}
  MAXD=${MEM_CRON_MAX:-120}         # max depth per tick — increased 40→120 (2 flat green cycles: the
                                    # window must keep ADVANCING into new territory, cases 40+ never seen by the
                                    # loop; deep ticks run in the background, without blocking the interval)
  CORPORA=(v3 v2 v1)
  DEPTHF="$RUNS/.cron-depth"
  ci=0; [ -f "$CURSOR" ] && ci=$(cat "$CURSOR" 2>/dev/null || echo 0)
  [[ "$ci" =~ ^[0-9]+$ ]] || ci=0
  d=0; [ -f "$DEPTHF" ] && d=$(cat "$DEPTHF" 2>/dev/null || echo 0)
  [[ "$d" =~ ^[0-9]+$ ]] || d=0
  CORPUS="${CORPORA[$(( ci % ${#CORPORA[@]} ))]}"
  # GROWING WINDOW: each tick explores DEEPER [0, HI) — the corpus is a linear conversation, so it is
  # replayed from 0 (--fresh) through HI. When the limit is reached, reset the depth and ROTATE the corpus → new coverage
  # without endlessly re-testing the same 10 (warning from the 4 flat ticks).
  HI=$(( N * (d + 1) ))
  [ "$HI" -ge "$MAXD" ] && { HI=$MAXD; echo 0 > "$DEPTHF"; echo $(( (ci + 1) % ${#CORPORA[@]} )) > "$CURSOR"; } \
                        || echo $(( d + 1 )) > "$DEPTHF"
  say "bot corpus=$CORPUS (fresh, range 0..$HI)"
  # generous tail: the runner prints "=== TANDA" ABOVE (before ~HI result lines) and
  # "Progreso acumulado" BELOW; as the window grows to MAXD(120), a short tail used to eat the
  # summary line → FAILN fell to 0 → the bot marked PASS despite failures (BLIND detector,
  # 2026-07-17). Source of truth = "Progreso acumulado" (ALWAYS at the end, survives the tail; with
  # --fresh it reflects ONLY this run); fallback to "=== TANDA".
  BOT_OUT=$(ZAELAR_DB="$HERE/memory/_data/zaelar.membot.db" MEM_PROCESSOR=1 \
            "$PY" -m tests.memory.e2e.bot.runner --fresh --range 0 "$HI" --corpus "$CORPUS" 2>&1 | tail -$(( MAXD + 40 )))
  echo "$BOT_OUT" >> "$LOG"
  BOT_LINE=$(echo "$BOT_OUT" | grep -E 'Progreso acumulado' | tail -1)
  [ -z "$BOT_LINE" ] && BOT_LINE=$(echo "$BOT_OUT" | grep -E '=== TANDA' | tail -1)
  if [ -z "$BOT_LINE" ]; then
    # There is NO summary line → the runner crashed (this is not a memory-gate failure). INFRA, not FIX.
    BOT_STATUS=INFRA; BOT_LINE="runner_sin_resumen (crash?)"
  else
    FAILN=$(echo "$BOT_LINE" | grep -oE '[0-9]+ fallos' | grep -oE '[0-9]+' | head -1)
    [ -z "$FAILN" ] && FAILN=0
    if [ "$FAILN" -gt 0 ]; then BOT_STATUS=FAIL; else BOT_STATUS=PASS; fi
  fi
  # Lines for the FAILED cases (so the agent knows WHAT to fix)
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
