#!/usr/bin/env bash
# Overnight autonomous test loop (INI-013). Runs the tester against a LIVE zaelar in a loop, rotating scenarios
# + free-form creative goals, so reports keep accumulating in tests/runs/agent/ for debugging. Robust: never crashes the
# loop on a single failure; sleeps between cycles. Stop: `pkill -f tests.voice.e2e.agent.overnight` or remove the cron.
#
# Model routing (operator 2026-07-07): DRIVE=DeepSeek(AIMLAPI), JUDGE=GLM(Z.AI)→DeepSeek fallback. Budget-capped by
# the plans themselves. Requires zaelar UP on :43917 (checked each cycle; skips if down so the cron can heal it).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
PY="$HERE/.venv/bin/python"
LOG="$HERE/tests/runs/agent/overnight.log"
mkdir -p "$HERE/tests/runs/agent"

# rotating menu: the scenarios (incl. V2-022 web-search, navegador/moto, mensajería, conectores) + creative
# free-form goals (a personal assistant — invent realistic asks). Kept in sync with tests/voice/e2e/agent/scenarios.py.
SCENARIOS=(conversation agenda memory widget search busqueda_web navegador_moto mensajeria conectores complex_idea chat paste websocket)
GOALS=(
  "Pídele a zaelar que muestre el reloj, luego el tiempo, luego cierra el reloj — comprueba que el canvas reacciona cada vez."
  "Pídele que te abra el widget de mensajería y te diga qué mensajes importantes tienes — NO debe crear un widget nuevo."
  "Pregunta qué widgets hay abiertos ahora mismo, y luego pídele que los cierre todos."
  "Dile que tu dentista es el martes a las 10; luego pídele que lo mueva al miércoles y confirma que la agenda se actualizó."
  "Pídele que te busque en Wallapop una bici de montaña de segunda mano por menos de 400 euros y te dé las mejores opciones."
  "Pregúntale qué tiempo hará este fin de semana en tu ciudad (dile una concreta) — quieres un dato rápido dicho de viva voz."
  "Ten una conversación real en castellano planeando un finde fuera, y luego pídele que recuerde el plan."
  "Pídele que busque quién ganó la última carrera de F1 y te lo cuente."
)

echo "=== overnight loop start $(date) ===" >> "$LOG"
i=0
while true; do
  # zaelar debe estar DEL TODO arriba (no solo el puerto): /api/livekit responde. Evita ciclos falsos-all-1s
  # cuando pillan a zaelar a medio reiniciar (una iteración del cron acaba de reiniciarlo). Espera hasta 40s.
  ready=0
  for _ in $(seq 1 20); do
    if curl -sf -m 3 http://127.0.0.1:43917/api/livekit >/dev/null 2>&1; then ready=1; break; fi
    sleep 2
  done
  if [ "$ready" != "1" ]; then
    echo "[$(date +%H:%M:%S)] zaelar no responde /api/livekit — salto ciclo (guard lo levantará)" >> "$LOG"
    sleep 30; continue
  fi
  sleep 3  # estabilización tras confirmar readiness
  if (( i % 2 == 0 )); then
    S="${SCENARIOS[$(( (i/2) % ${#SCENARIOS[@]} ))]}"
    echo "[$(date +%H:%M:%S)] cycle $i → scenario=$S" >> "$LOG"
    "$PY" -m tests.voice.e2e.agent.run --scenario "$S" --no-open --hold 0 >> "$LOG" 2>&1 || echo "  (cycle errored, continuing)" >> "$LOG"
  else
    G="${GOALS[$(( (i/2) % ${#GOALS[@]} ))]}"
    echo "[$(date +%H:%M:%S)] cycle $i → goal: ${G:0:60}…" >> "$LOG"
    "$PY" -m tests.voice.e2e.agent.run --goal "$G" --turns 6 --no-open --hold 0 >> "$LOG" 2>&1 || echo "  (cycle errored, continuing)" >> "$LOG"
  fi
  i=$((i+1))
  sleep 20
done
