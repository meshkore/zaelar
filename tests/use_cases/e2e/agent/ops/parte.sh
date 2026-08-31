#!/bin/zsh
# The hourly REPORT: four numbers and the latest breakdowns. Deliberately short.
#
# The operator asked for “a simple, short numerical summary every hour” (2026-08-28). What it does NOT do, and
# deliberately so: it does not interpret, recommend, or repeat the judge’s verdict. A report that grows longer stops
# being read, and then it makes no difference how well written it is.
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

# Rounds from the last hour, from the supervisor’s log.
d = Path("tests/runs/use_cases/supervisor/diario.jsonl")
filas = []
if d.exists():
    for l in d.read_text(encoding="utf-8").splitlines():
        try:
            f = json.loads(l)
        except Exception:
            continue
        # `t` is a FORMATTED TIMESTAMP ('2026-08-27 07:20:40'), not epoch time. Reading it as a number does not fail
        # silently; it blows up — but a lazy `except` here would have left the report saying “0 rounds” forever,
        # which is the silent failure.
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

# Which brain is being measured — the V2-415 seal. If anything other than the headline appears, it is visible here.
cerebros = {}
for v in board.values():
    b = v.get("brain")
    if b:
        cerebros[b] = cerebros.get(b, 0) + 1
if cerebros:
    print("   cerebro:  " + ", ".join(f"{k}×{v}" for k, v in sorted(cerebros.items(), key=lambda kv: -kv[1])[:3]))
PY
