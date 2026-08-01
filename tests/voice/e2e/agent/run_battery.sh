#!/usr/bin/env bash
# run_battery.sh — corre TODO el catálogo de escenarios (tests/voice/e2e/agent/scenarios.py) contra un zaelar VIVO, uno por uno,
# con watchdog por escenario (macOS no tiene `timeout`), e imprime una línea de resumen por escenario + una tabla
# final. Para la prueba completa que pide el operador. Requiere zaelar UP. Exit 0 siempre (se lee la salida).
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
PY="$HERE/.venv/bin/python"
RUNS="$HERE/tests/runs/agent"; mkdir -p "$RUNS"
MAX_RUN=${BATTERY_MAX_RUN:-360}
URL="http://127.0.0.1:43917"

# orden: casos rápidos primero, tareas de navegador (lentas) al final
SCENARIOS=(${BATTERY_SCENARIOS:-conversation agenda memory widget search busqueda_web mensajeria conectores complex_idea chat paste archivos websocket navegador_moto navegador_coche youtube_voice reserva_web musica musica_difusa musica_spotify_connect})

if ! curl -sf -m 4 "$URL/api/livekit" >/dev/null 2>&1; then echo "zaelar NO responde /api/livekit — abortando"; exit 0; fi

echo "=== BATTERY START $(date +%H:%M:%S) · ${#SCENARIOS[@]} escenarios ==="
SUMMARY="$RUNS/battery_summary_$(date +%H%M%S).tsv"
echo -e "scenario\tstatus\toverall\tnat\tcoh\tuti\tacc\tlat\trob\tveredicto" > "$SUMMARY"

SETTLE=${BATTERY_SETTLE:-12}   # pausa entre escenarios: deja al worker THREAD liberar la sala anterior (evita
                               # mutes/timeouts falsos por contención — la causa de los all-1s de la 1ª batería)
first=1
for S in "${SCENARIOS[@]}"; do
  if [ "$first" = "1" ]; then first=0; else
    # readiness + settle antes del siguiente escenario
    for _ in $(seq 1 20); do curl -sf -m 3 "$URL/api/livekit" >/dev/null 2>&1 && break; sleep 2; done
    sleep "$SETTLE"
  fi
  echo "--- $(date +%H:%M:%S) scenario=$S ---"
  "$PY" -m tests.voice.e2e.agent.run --scenario "$S" --no-open --hold 0 >> "$RUNS/battery.log" 2>&1 &
  RUN_PID=$!
  ( sleep "$MAX_RUN"; kill -0 "$RUN_PID" 2>/dev/null && { echo "  [$S] >${MAX_RUN}s → kill"; kill -TERM "$RUN_PID" 2>/dev/null; sleep 3; kill -9 "$RUN_PID" 2>/dev/null; } ) &
  WPID=$!
  wait "$RUN_PID" 2>/dev/null || true
  kill "$WPID" 2>/dev/null || true

  NEWEST=$(ls -t "$RUNS"/report_*.json 2>/dev/null | head -1)
  "$PY" - "$NEWEST" "$S" "$SUMMARY" <<'PYEOF'
import sys, json
path, scen, summ = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    d = json.load(open(path)); r = (d.get("results") or [{}])[0]
    v = r.get("verdict") or {}; run = r.get("run") or {}; sc = v.get("scores") or {}
    ov = v.get("overall")
    infra = bool(run.get("dispatch_dead_after_retry")) or ov is None or sc == {}
    st = "INFRA" if infra else ("PASS" if (ov or 0) >= 4 else "FAIL")
    g = lambda k: sc.get(k, "-")
    row = [scen, st, str(ov), str(g("naturalidad")), str(g("coherencia")), str(g("utilidad")),
           str(g("accion")), str(g("latencia")), str(g("robustez")), str(v.get("veredicto",""))[:160]]
    open(summ, "a").write("\t".join(row) + "\n")
    print(f"  → {st} overall={ov} scores={sc} lat={g('latencia')}")
except Exception as e:
    open(summ, "a").write(f"{scen}\tERROR\t-\t-\t-\t-\t-\t-\t-\t{e}\n")
    print(f"  → ERROR {e}")
PYEOF
done

echo "=== BATTERY DONE $(date +%H:%M:%S) ==="
echo "=== SUMMARY ==="; column -t -s$'\t' "$SUMMARY" 2>/dev/null || cat "$SUMMARY"
echo "summary → $SUMMARY"

# Archivo del día (histórico consultable): tests/voice/e2e/agent/reports/<YYYYMMDD>-<desc>/ — ver zaelar-testing.md §archiva.
DESC=${BATTERY_DESC:-bateria}
ARCH="$HERE/tests/voice/e2e/agent/reports/$(date +%Y%m%d)-$DESC"
mkdir -p "$ARCH"
cp "$SUMMARY" "$ARCH/" 2>/dev/null || true
# copia los informes de esta tanda (los más recientes, uno por escenario corrido)
ls -t "$RUNS"/report_*.json "$RUNS"/report_*.md 2>/dev/null | head -$(( ${#SCENARIOS[@]} * 2 )) | while read f; do cp "$f" "$ARCH/" 2>/dev/null || true; done
if [ ! -f "$ARCH/INFORME.md" ]; then
  { echo "# Informe de test — $(date +%Y-%m-%d) · $DESC"; echo;
    echo "Batería de ${#SCENARIOS[@]} escenarios. Rellenar: hallazgos (bug real vs ruido de STT vs rigidez del juez),";
    echo "arreglos, latencias antes/después, y para navegación el veredicto HUMANO de datos extraídos (✋).";
    echo; echo '## Tabla de resultados'; echo '```'; column -t -s$'\t' "$SUMMARY" 2>/dev/null || cat "$SUMMARY"; echo '```';
  } > "$ARCH/INFORME.md"
fi
echo "archivo del día → $ARCH"
