#!/bin/zsh
# El PARTE horario: cuatro números y las últimas averías. Corto a propósito.
#
# El operador pidió «un resumen numérico cada hora, simple y corto» (2026-08-28). Lo que NO hace, y es
# deliberado: no interpreta, no recomienda y no repite el veredicto del juez. Un parte que se alarga deja
# de leerse, y entonces da igual lo bien escrito que esté.
set -u
cd "$(dirname "$0")/../../../../.." || exit 1     # → engine/
./.venv/bin/python - "$@" <<'PY'
import json, sys, time
from pathlib import Path

desde = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
board = json.loads(Path("tests/use_cases/status.json").read_text(encoding="utf-8")).get("scenarios") or {}

def cuenta(estado, loc):
    return sum(1 for k, v in board.items()
               if v.get("state") == estado and (k.endswith("__us") if loc == "us" else not k.endswith("__us")))

print(f"⏱  {time.strftime('%H:%M')} · plató 24/7")
print(f"        PASS  FAIL  INFRA  CAPPED")
for loc in ("es", "us"):
    print(f"   {loc.upper()}   {cuenta('PASS',loc):>4}  {cuenta('FAIL',loc):>4}  "
          f"{cuenta('INFRA',loc):>5}  {cuenta('CAPPED',loc):>6}")

# Rondas de la última hora, del diario del supervisor.
d = Path("tests/runs/use_cases/supervisor/diario.jsonl")
filas = []
if d.exists():
    for l in d.read_text(encoding="utf-8").splitlines():
        try:
            f = json.loads(l)
        except Exception:
            continue
        # `t` es una MARCA FORMATEADA ('2026-08-27 07:20:40'), no epoch. Leerla como número no falla en
        # silencio, revienta — pero un `except` perezoso aquí habría dejado el parte diciendo «0 rondas»
        # para siempre, que sí es el fallo callado.
        try:
            ts = time.mktime(time.strptime(str(f.get("t") or ""), "%Y-%m-%d %H:%M:%S"))
        except Exception:
            continue
        if ts >= desde:
            filas.append(f)
res = {}
for f in filas:
    r = str(f.get("resultado") or "?")
    res[r] = res.get(r, 0) + 1
print(f"   rondas en el tramo: {len(filas)}" + (f"  ({', '.join(f'{k}×{v}' for k, v in sorted(res.items()))})" if res else ""))

# Con qué cerebro se está midiendo — el sello de V2-415. Si sale algo que no es el titular, se ve aquí.
cerebros = {}
for v in board.values():
    b = v.get("brain")
    if b:
        cerebros[b] = cerebros.get(b, 0) + 1
if cerebros:
    print("   cerebro:  " + ", ".join(f"{k}×{v}" for k, v in sorted(cerebros.items(), key=lambda kv: -kv[1])[:3]))
PY
