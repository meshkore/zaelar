"""rem_synth_bench.py — bench del modelo de SÍNTESIS del sueño REM (V2-056, 2026-07-20).

Pasa a cada candidato la tarea REAL (`nucleo/memllm.synthesize_concept_groups`, mismo prompt/parseo que usa el
sueño) sobre 3 grupos-fixture con hechos conocidos, y puntúa MECÁNICAMENTE:
  - validez (devuelve un item por grupo, insight no-nulo donde hay sustancia)
  - retención de DATOS CLAVE (nombres propios/cifras deben sobrevivir a la síntesis — regla anti-T181)
  - castellano (regla monolingüe)
  - brevedad (≤ 260 chars/insight — un insight no es un resumen-lista)
  - abstracción (el insight NO repite verbatim una píldora — debe sintetizar)
Uso: PYTHONPATH=. ./.venv/bin/python tests/memory/e2e/bot/rem_synth_bench.py
Veredictos → zaelar-model-benchmarks.md §12.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
import unicodedata
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
load_dotenv(REPO / ".env")

from nucleo import memllm  # noqa: E402

AIMLAPI = "https://api.aimlapi.com/v1"
CANDIDATES = {
    "gpt-4.1-mini":      ("https://api.openai.com/v1", "gpt-4.1-mini"),
    "claude-haiku-4.5":  (AIMLAPI, "anthropic/claude-haiku-4.5"),
    "gemini-2.5-flash":  (AIMLAPI, "google/gemini-2.5-flash"),
    "deepseek-v4-flash": (AIMLAPI, "deepseek/deepseek-v4-flash"),
}

GROUPS = [
    {"concept": "musica", "pills": [
        "Escuchó a Mocedades («Tómame o Déjame») por la tarde mientras trabajaba.",
        "Pidió música de los ochenta en español.",
        "Sonó Serrat en la sesión de trabajo del jueves.",
        "Compró entradas para el concierto de Muse en Bilbao el 12 de septiembre.",
        "Pidió que la música no se interrumpa cuando llega un mensaje.",
    ], "keys": [["muse"], ["bilbao"], ["ochenta", "80"]]},
    {"concept": "salud", "pills": [
        "Es alérgico a la penicilina.",
        "Es alérgico al marisco.",
        "Va al gimnasio los lunes y jueves a las siete.",
        "Ha notado que rinde mejor por las mañanas.",
        "Dejó el café en enero.",
    ], "keys": [["penicilina"], ["marisco"], ["gimnasio"]]},
    {"concept": "familia", "pills": [
        "Su mujer se llama Marta.",
        "Tiene gemelos, Pau y Nil, de 6 años.",
        "Su madre vive con ellos en Soria.",
        "Los domingos comen todos juntos en casa.",
        "Marta trabaja de enfermera en el hospital de Soria.",
    ], "keys": [["marta"], ["pau"], ["nil"]]},
]

_ES_HINTS = ("le ", "su ", "los ", "de ", "que ", "es ", "tiene", "suele", "prefiere", "va ")


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(c) != "Mn")


def score(results: list[dict]) -> tuple[float, float, list[str]]:
    total = got = 0.0
    notes = []
    by_c = {r["concept"]: r.get("insight") for r in results}
    for g in GROUPS:
        ins = by_c.get(g["concept"]) or ""
        total += 2 + len(g["keys"])                     # 1 validez + 1 forma + keys
        if not ins:
            notes.append(f"{g['concept']}: SIN insight")
            continue
        got += 1                                        # validez
        n = _norm(ins)
        form_ok = (len(ins) <= 260 and any(h in " " + n for h in _ES_HINTS)
                   and not any(_norm(p) == n for p in g["pills"]))
        got += 1 if form_ok else 0
        hits = sum(1 for grp in g["keys"] if any(_norm(k) in n for k in grp))
        got += hits
        notes.append(f"{g['concept']}: keys {hits}/{len(g['keys'])} form={'ok' if form_ok else 'MAL'} | {ins[:110]}")
    return got, total, notes


def main() -> None:
    out_rows = []
    for name, (url, model) in CANDIDATES.items():
        print(f"→ {name} …", flush=True)
        lats, runs = [], []
        for _ in range(2):                              # 2 pasadas (estabilidad)
            t0 = time.time()
            res = memllm.synthesize_concept_groups(GROUPS, model_override=model, url_override=url)
            lats.append(round((time.time() - t0) * 1000))
            runs.append(score(res))
        pts = statistics.mean(r[0] for r in runs)
        tot = runs[0][1]
        out_rows.append({"model": name, "score": round(pts, 1), "total": tot,
                         "pct": round(100 * pts / tot, 1), "p50_ms": int(statistics.median(lats)),
                         "notes": runs[-1][2]})
        print(f"   {out_rows[-1]['pct']}%  p50={out_rows[-1]['p50_ms']}ms")

    out = Path(__file__).parent / "resultados" / f"{time.strftime('%Y%m%d')}-rem-synth-bench"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(out_rows, ensure_ascii=False, indent=2))
    lines = ["# Bench de SÍNTESIS REM — " + time.strftime("%Y-%m-%d %H:%M"), "",
             "| modelo | score | % | p50 ms |", "|---|---|---|---|"]
    for r in sorted(out_rows, key=lambda x: -x["pct"]):
        lines.append(f"| {r['model']} | {r['score']}/{r['total']} | {r['pct']}% | {r['p50_ms']} |")
    (out / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
