#!/usr/bin/env bash
# cron_tick.sh — ONE test tick for the 15-minute test→fix cron (INI-013 §Cron test→fix loop).
# Deterministic half of the loop (the Claude agent does the judging/fixing half):
#   1) ensure zaelar is UP on :43917 (make run + readiness wait if down)
#   2) if the operator is LIVE in a voice session, SKIP this tick (don't contend the single THREAD worker)
#   3) pick the NEXT scenario round-robin (cursor persisted in tests/runs/agent/.cron-cursor)
#   4) run exactly that one scenario (black-box, no browser, no lingering)
#   5) print a compact VERDICT block the agent parses to decide PASS / FIX / INFRA
# Never creates profiles; runs against the LIVE account (operator-authorized). Exit 0 always (agent reads output).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
PY="$HERE/.venv/bin/python"
RUNS="$HERE/tests/runs/agent"; mkdir -p "$RUNS"
CURSOR="$RUNS/.cron-cursor"
URL="http://127.0.0.1:43917"

# curated rotation — meaningful, complete use-cases (kept in sync with tests/voice/e2e/agent/scenarios.py)
SCENARIOS=(mensajeria widget navegador_moto reserva_web musica musica_difusa musica_spotify_connect youtube_voice conectores memory search busqueda_web agenda complex_idea conversation chat paste archivos websocket)

say(){ echo "[cron_tick $(date +%H:%M:%S)] $*"; }

# 1) zaelar up?
if ! curl -sf -m 4 "$URL/api/brain" >/dev/null 2>&1; then
  say "zaelar down → make run (detached)"
  ( cd "$HERE" && nohup make run >> "$RUNS/zaelar.log" 2>&1 & )
  for _ in $(seq 1 90); do curl -sf -m 3 "$URL/api/livekit" >/dev/null 2>&1 && break; sleep 1; done
fi
if ! curl -sf -m 4 "$URL/api/livekit" >/dev/null 2>&1; then
  echo "VERDICT status=INFRA scenario=- reason=zaelar_not_ready"; exit 0
fi

# 2) operator live? (voice health = ok/active means someone is in a session) → skip to avoid worker contention
VOICE_STATE=$(curl -sf -m 4 "$URL/api/status" 2>/dev/null | "$PY" -c "import sys,json
try:
    d=json.load(sys.stdin); items={i['key']:i for i in d.get('items',[])}
    print(items.get('voice',{}).get('state','off'))
except Exception: print('off')" 2>/dev/null || echo off)
if [ "$VOICE_STATE" = "ok" ] || [ "$VOICE_STATE" = "on" ] || [ "$VOICE_STATE" = "active" ]; then
  echo "VERDICT status=SKIP scenario=- reason=operator_live_voice"; exit 0
fi

# 3) next scenario (round-robin)
idx=0; [ -f "$CURSOR" ] && idx=$(cat "$CURSOR" 2>/dev/null || echo 0)
[[ "$idx" =~ ^[0-9]+$ ]] || idx=0
S="${SCENARIOS[$(( idx % ${#SCENARIOS[@]} ))]}"
echo $(( (idx + 1) % ${#SCENARIOS[@]} )) > "$CURSOR"
say "scenario=$S (cursor $idx)"

# 4) run it — with a portable watchdog (macOS has no `timeout`): kill the run if it exceeds MAX_RUN seconds
MAX_RUN=${CRON_TICK_MAX_RUN:-300}
"$PY" -m tests.voice.e2e.agent.run --scenario "$S" --no-open --hold 0 >> "$RUNS/cron.log" 2>&1 &
RUN_PID=$!
( sleep "$MAX_RUN"; kill -0 "$RUN_PID" 2>/dev/null && { say "run exceeded ${MAX_RUN}s → killing"; kill -TERM "$RUN_PID" 2>/dev/null; sleep 3; kill -9 "$RUN_PID" 2>/dev/null; } ) &
WATCH_PID=$!
wait "$RUN_PID" 2>/dev/null || say "run errored/killed (continuing — verdict below)"
kill "$WATCH_PID" 2>/dev/null || true

# 5) compact verdict from the newest report JSON
NEWEST=$(ls -t "$RUNS"/report_*.json 2>/dev/null | head -1)
"$PY" - "$NEWEST" "$S" <<'PYEOF'
import sys, json
path, scen = (sys.argv[1] if len(sys.argv)>1 else ""), (sys.argv[2] if len(sys.argv)>2 else "?")
try:
    d = json.load(open(path))
    r = (d.get("results") or [{}])[0]
    v = r.get("verdict") or {}
    run = r.get("run") or {}
    scores = v.get("scores") or {}
    overall = v.get("overall")
    infra = bool(run.get("dispatch_dead_after_retry")) or overall is None or scores == {}
    status = "INFRA" if infra else ("PASS" if (overall or 0) >= 4 else "FAIL")
    print(f"VERDICT status={status} scenario={scen} overall={overall} report={path}")
    print("SCORES " + json.dumps(scores, ensure_ascii=False))
    print("VEREDICTO " + str(v.get("veredicto","")).strip()[:400])
    for f in (v.get("findings") or [])[:5]:
        print("FINDING " + json.dumps(f, ensure_ascii=False)[:300])
    for im in (v.get("improvements") or [])[:5]:
        print("IMPROVE " + json.dumps(im, ensure_ascii=False)[:300])
except Exception as e:
    print(f"VERDICT status=INFRA scenario={scen} overall=None report={path} err={e}")
PYEOF
