"""rem_synth_bench.py — REM sleep SYNTHESIS model benchmark (V2-056 · 2026-08-09 round).

Passes each candidate the REAL task (`nucleo/memllm.synthesize_concept_groups`, using the same prompt/parsing as
sleep) over 8 fixture groups with known facts, 3 runs, and scores it MECHANICALLY.

**QUALITY matters here, not price — the opposite of the HEART benchmark** (§12.3). Structural reason, not opinion:
`memory/rem.py` sends ALL groups in **A single call** (`memllm.synthesize_concept_groups`), with
`MAX_GROUPS=8` groups × `pills[:12]` pills, **once a day** (`rem_every_hours=24`). That is about 365 calls per
year per user with the input bounded by design: **cost does NOT scale with memory size**. A model that costs 10×
more still costs cents per year, while a bad insight contaminates long-term memory (it is written with
`slot=insight:<concept>`, which the retriever may return as if it were an operator fact).
$/sleep is reported as well, so the decision is informed rather than an act of faith.

SIX axes:
  1. VALIDITY       — returns one well-formed item per group.
  2. KEYS           — proper names / figures / dates SURVIVE synthesis (anti-T181 rule: generalizing
                      “has two children” where it said “Pau and Nil” destroys the data).
  3. FORM           — Spanish (monolingual rule), ≤260 chars, and do NOT copy a pill verbatim (it is synthesis,
                      not a list-summary).
  4. NULL DISCIPLINE — a WEAK group must return `insight: null` (the prompt requires it). Inventing an insight
                      from three trivialities is worse than giving none. The old benchmark did NOT measure this.
  5. NON-INVENTION  — the insight cannot assert anything NOT present in the pills (a list of forbidden terms per
                      group, plausible but absent). This is the MOST costly failure: a consolidated hallucination
                      enters durable memory appearing to be a fact.
  6. $/SLEEP and $/YEAR — using REAL tokens (`memllm.last_usage()`) × published rates (`prices.json`).

Usage: PYTHONPATH=. ./.venv/bin/python tests/memory/e2e/bot/rem_synth_bench.py [--models a,b] [--runs 3] [--preflight]
Verdicts → zaelar-model-benchmarks.md §12.4.
"""
from __future__ import annotations

import argparse
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
load_dotenv(REPO / ".meshkore/credentials/zaelar.env", override=True)

from nucleo import memllm  # noqa: E402

AIML = "https://api.aimlapi.com/v1"
OPENAI = "https://api.openai.com/v1"

# COMMERCIAL API candidates. Since the cost is negligible (1 call/day), the sweep includes
# POWERFUL and REASONING models that were rejected in the HEART benchmark due to price or polluting discards — here
# there are no discards to pollute, and there is an abstraction task where a reasoning model could genuinely help.
CANDIDATES: dict[str, tuple[str, str]] = {
    "gpt-4.1-mini":          (AIML, "openai/gpt-4.1-mini"),        # current LEADER (inherited from §12.2)
    "deepseek-v4-flash":     (AIML, "deepseek/deepseek-v4-flash"),  # tied the leader in §12.2; the HEART one
    "deepseek-v4-pro":       (AIML, "deepseek/deepseek-v4-pro"),    # the POWERFUL DeepSeek
    "deepseek-thinking":     (AIML, "deepseek/deepseek-thinking-v3.2-exp"),   # DeepSeek reasoning model
    "deepseek-reasoner":     (AIML, "deepseek/deepseek-reasoner"),
    "gemini-2.5-flash":      (AIML, "google/gemini-2.5-flash"),     # 50% in §12.2 — control
    "gemini-2.5-pro":        (AIML, "google/gemini-2.5-pro"),
    "gpt-5-mini":            (AIML, "openai/gpt-5-mini"),           # reasoning model
    "gpt-4.1":               (AIML, "openai/gpt-4.1"),
    "kimi-k2-6":             (AIML, "moonshot/kimi-k2-6"),
    "glm-4.7":               (AIML, "zhipu/glm-4.7"),
    "grok-4-fast-nonreason": (AIML, "x-ai/grok-4-fast-non-reasoning"),
    "gpt-4.1-mini@openai":   (OPENAI, "gpt-4.1-mini"),              # the path used before 2026-08-09
}

PRICES: dict[str, tuple[float, float]] = {}

# Fixture groups. `keys` = data that MUST survive; `forbidden` = plausible terms ABSENT from the
# pills (if they appear, the model invented them); `want_null` = weak group that does NOT deserve an insight.
GROUPS_SPEC: list[dict] = [
    {"concept": "musica", "want_null": False,
     "pills": [
         "Escuchó a Mocedades («Tómame o Déjame») por la tarde mientras trabajaba.",
         "Pidió música de los ochenta en español.",
         "Sonó Serrat en la sesión de trabajo del jueves.",
         "Compró entradas para el concierto de Muse en Bilbao el 12 de septiembre.",
         "Pidió que la música no se interrumpa cuando llega un mensaje.",
     ],
     "keys": [["muse"], ["bilbao"], ["ochenta", "80"]],
     "forbidden": ["jazz", "rock progresivo", "vinilo", "guitarra"]},
    {"concept": "salud", "want_null": False,
     "pills": [
         "Es alérgico a la penicilina.",
         "Es alérgico al marisco.",
         "Va al gimnasio los lunes y jueves a las siete.",
         "Ha notado que rinde mejor por las mañanas.",
         "Dejó el café en enero.",
     ],
     "keys": [["penicilina"], ["marisco"], ["gimnasio"]],
     "forbidden": ["diabetes", "vegetariano", "fumador", "asma", "colesterol"]},
    {"concept": "familia", "want_null": False,
     "pills": [
         "Su mujer se llama Marta.",
         "Tiene gemelos, Pau y Nil, de 6 años.",
         "Su madre vive con ellos en Soria.",
         "Los domingos comen todos juntos en casa.",
         "Marta trabaja de enfermera en el hospital de Soria.",
     ],
     "keys": [["marta"], ["pau"], ["nil"]],
     "forbidden": ["divorci", "hermano", "perro", "gato"]},
    # NEW — EVOLUTION/contradiction: the insight must reflect the CURRENT state, without averaging or contradicting itself.
    {"concept": "vivienda", "want_null": False,
     "pills": [
         "Antes vivía en Madrid.",
         "Se mudó a Valencia hace unas semanas.",
         "En Madrid vivía de alquiler, 1.100 euros al mes.",
         "En Valencia ha comprado piso con una hipoteca de 250.000 euros a 30 años.",
         "Le gusta que Valencia esté cerca del mar.",
     ],
     "keys": [["valencia"], ["250.000", "250000"], ["hipoteca"]],
     "forbidden": ["barcelona", "sevilla", "alquilado en valencia", "vuelve a madrid"]},
    # NEW — dense FIGURES and DATES (strict anti-T181).
    {"concept": "trabajo", "want_null": False,
     "pills": [
         "Es coordinador de emergencias desde marzo.",
         "Antes fue bombero durante 12 años.",
         "Su jefa se llama Marta Ruiz.",
         "Entrega el informe trimestral el 15 de cada trimestre.",
         "Tiene guardias los fines de semana alternos.",
         "Cobra 2.400 euros netos al mes.",
     ],
     "keys": [["coordinador"], ["12"], ["marta ruiz", "ruiz"], ["2.400", "2400"]],
     "forbidden": ["director", "despedido", "jubila", "ascenso"]},
    # NEW — LARGE GROUP (12 pills, the actual `pills[:12]` limit): it must not lose key data.
    {"concept": "viajes", "want_null": False,
     "pills": [
         "El mes pasado viajó a Oporto y le encantó.",
         "De pequeño pasaba los veranos en Segovia con sus abuelos.",
         "Quiere hacer un viaje de buceo el año que viene.",
         "Le interesa el buceo.",
         "Voló a Berlín en 2023 por trabajo.",
         "No le gustan los vuelos de más de 8 horas.",
         "Prefiere viajar en temporada baja.",
         "Tiene el pasaporte caducado desde febrero.",
         "Su presupuesto de vacaciones es de 3.000 euros máximo.",
         "Suele viajar con Marta.",
         "En Oporto visitó las bodegas de vino.",
         "Quiere volver a Mallorca algún día.",
     ],
     "keys": [["oporto"], ["buceo"], ["3.000", "3000"], ["pasaporte"]],
     "forbidden": ["japón", "crucero", "caravana", "esquí"]},
    # NEW — MULTILINGUAL: pills in another language, insight ALWAYS in Spanish (monolingual rule).
    {"concept": "estudios", "want_null": False,
     "pills": [
         "Le interesa cada vez más la arquitectura.",
         "He is reading about fire-safe building design.",
         "Vol estudiar arquitectura de manera seriosa.",
         "Se apuntó a un curso online de estructuras en enero.",
     ],
     "keys": [["arquitectura"]],
     "forbidden": ["medicina", "derecho", "máster en harvard"]},
    # NEW — NULL DISCIPLINE: trivialities without a pattern. The prompt REQUIRES a null insight here.
    {"concept": "cotidiano", "want_null": True,
     "pills": [
         "Esta mañana tomó un café.",
         "Ayer estaba cansado.",
         "Hoy ha hecho buen tiempo.",
         "Se le olvidó dónde dejó las llaves.",
     ],
     "keys": [],
     "forbidden": ["insomnio", "depresión", "rutina matutina estricta", "problema de memoria"]},
]

GROUPS = [{"concept": g["concept"], "pills": g["pills"]} for g in GROUPS_SPEC]

_ES_HINTS = ("le ", "su ", "los ", "de ", "que ", "es ", "tiene", "suele", "prefiere", "va ")


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(c) != "Mn")


def score(results: list[dict]) -> tuple[dict, list[str]]:
    """Returns (points by axis, notes). Each axis is aggregated separately (they are not merged into a %)."""
    ax = {k: [0, 0] for k in ("validez", "claves", "forma", "null", "no_invencion")}   # [got, total]
    notes: list[str] = []
    by_c = {r["concept"]: r.get("insight") for r in results}
    # ARTIFACT to avoid (seen in the 2026-08-09 round): a model that returns NOTHING passed the `null` axis
    # at 100% —the weak group “came out null,” of course, like all of them— and earned 20% quality instead of 0%.
    # A no-result is not discipline. If there is not a single insight in substantive groups, `null` does not score.
    produjo_algo = any((by_c.get(g["concept"]) or "") for g in GROUPS_SPEC if not g["want_null"])
    for g in GROUPS_SPEC:
        c = g["concept"]
        ins = by_c.get(c) or ""
        n = _norm(ins)
        if g["want_null"]:
            if produjo_algo:                       # see `produjo_algo`: saying nothing at all is not discipline
                ax["null"][1] += 1
                if not ins:
                    ax["null"][0] += 1
            # A group that should be null does not score on the other axes, but DOES score on non-invention if it spoke.
            if ins:
                notes.append(f"{c}: DEBÍA ser null y sintetizó → «{ins[:90]}»")
                ax["no_invencion"][1] += 1
                bad = [f for f in g["forbidden"] if _norm(f) in n]
                ax["no_invencion"][0] += 0 if bad else 1
                if bad:
                    notes.append(f"{c}: INVENTÓ {bad}")
            continue
        ax["validez"][1] += 1
        if not ins:
            notes.append(f"{c}: SIN insight (debía tenerlo)")
            ax["claves"][1] += len(g["keys"])
            ax["forma"][1] += 1
            ax["no_invencion"][1] += 1
            continue
        ax["validez"][0] += 1
        # keys
        for grp in g["keys"]:
            ax["claves"][1] += 1
            if any(_norm(k) in n for k in grp):
                ax["claves"][0] += 1
            else:
                notes.append(f"{c}: PERDIÓ la clave {grp[0]!r}")
        # form
        ax["forma"][1] += 1
        es_ok = any(h in " " + n for h in _ES_HINTS)
        brief_ok = len(ins) <= 260
        not_verbatim = not any(_norm(p) == n for p in g["pills"])
        if es_ok and brief_ok and not_verbatim:
            ax["forma"][0] += 1
        else:
            why = [w for w, ok in (("no-es", es_ok), ("largo", brief_ok), ("verbatim", not_verbatim)) if not ok]
            notes.append(f"{c}: FORMA {why} ({len(ins)} chars) «{ins[:90]}»")
        # non-invention
        ax["no_invencion"][1] += 1
        bad = [f for f in g["forbidden"] if _norm(f) in n]
        ax["no_invencion"][0] += 0 if bad else 1
        if bad:
            notes.append(f"{c}: INVENTÓ {bad} → «{ins[:90]}»")
    return ax, notes


def _pct(pair) -> float | None:
    """None = axis NOT APPLICABLE in this run (e.g. `null` when the model produced nothing). Returning 100.0
    there would be misleading: a no-result would be read as perfect discipline."""
    return round(100 * pair[0] / pair[1], 1) if pair[1] else None


def _load_prices() -> None:
    p = Path(__file__).parent / "prices.json"
    if p.exists():
        PRICES.update({k: tuple(v) for k, v in json.loads(p.read_text()).items() if not k.startswith("_")})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=",".join(CANDIDATES))
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    _load_prices()
    names = [m.strip() for m in args.models.split(",") if m.strip() and m.strip() in CANDIDATES]

    if args.preflight:
        print(f"PREFLIGHT — {len(names)} candidatos")
        for name in names:
            url, model = CANDIDATES[name]
            t0 = time.time()
            r = memllm.synthesize_concept_groups(GROUPS[:1], model_override=model, url_override=url)
            ms = round((time.time() - t0) * 1000)
            print(f"  {'OK   ' if r else 'FALLO'} {name:24s} {ms:6d}ms  {len(r)} insight(s)", flush=True)
        return

    out_rows = []
    for name in names:
        url, model = CANDIDATES[name]
        print(f"→ {name} …", flush=True)
        lats, axes, usages, notes = [], [], [], []
        for _ in range(max(1, args.runs)):
            t0 = time.time()
            res = memllm.synthesize_concept_groups(GROUPS, model_override=model, url_override=url)
            lats.append(round((time.time() - t0) * 1000))
            u = memllm.last_usage()
            if u.get("prompt_tokens"):
                usages.append(u)
            ax, nt = score(res)
            axes.append(ax)
            notes = nt
        agg = {k: [sum(a[k][0] for a in axes) / len(axes), axes[0][k][1]] for k in axes[0]}
        avg_in = round(statistics.mean(u["prompt_tokens"] for u in usages)) if usages else 0
        avg_out = round(statistics.mean(u.get("completion_tokens") or 0 for u in usages)) if usages else 0
        rate = PRICES.get(name)
        per_sleep = ((avg_in / 1e6) * rate[0] + (avg_out / 1e6) * rate[1]) if (rate and avg_in) else None
        row = {"model": name, "endpoint": url, "model_id": model,
               "validez": _pct(agg["validez"]), "claves": _pct(agg["claves"]), "forma": _pct(agg["forma"]),
               "null": _pct(agg["null"]), "no_invencion": _pct(agg["no_invencion"]),
               "usd_per_sleep": round(per_sleep, 5) if per_sleep is not None else None,
               "usd_per_year": round(per_sleep * 365, 3) if per_sleep is not None else None,
               "avg_in_tok": avg_in, "avg_out_tok": avg_out,
               "p50_ms": int(statistics.median(lats)), "runs": len(axes), "notes": notes}
        # Average of the FIVE quality axes — a summary, not a substitute for examining them separately.
        _ejes = [row[k] for k in ("validez", "claves", "forma", "null", "no_invencion") if row[k] is not None]
        row["calidad_pct"] = round(statistics.mean(_ejes), 1) if _ejes else 0.0
        out_rows.append(row)
        _f = lambda v: "n/a" if v is None else v
        print(f"   calidad={row['calidad_pct']}%  (val={_f(row['validez'])} claves={_f(row['claves'])} "
              f"forma={_f(row['forma'])} null={_f(row['null'])} no-inv={_f(row['no_invencion'])})  "
              f"${row['usd_per_year']}/año  p50={row['p50_ms']}ms", flush=True)

    tag = f"-{args.tag}" if args.tag else ""
    out = Path(__file__).parent / "resultados" / f"{time.strftime('%Y%m%d')}-rem-synth-bench{tag}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(out_rows, ensure_ascii=False, indent=2))
    lines = [f"# Bench de SÍNTESIS REM — {time.strftime('%Y-%m-%d %H:%M')}", "",
             f"{len(GROUPS_SPEC)} grupos · {args.runs} pasada(s) · manda la CALIDAD (1 llamada/día, coste acotado)",
             "", "| modelo | calidad | validez | claves | forma | null | no-invención | $/año | p50 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(out_rows, key=lambda x: -x["calidad_pct"]):
        cost = f"${r['usd_per_year']}" if r["usd_per_year"] is not None else "—"
        _c = lambda v: "n/a" if v is None else f"{v}%"
        lines.append(f"| {r['model']} | **{r['calidad_pct']}%** | {_c(r['validez'])} | {_c(r['claves'])} | "
                     f"{_c(r['forma'])} | {_c(r['null'])} | {_c(r['no_invencion'])} | {cost} | {r['p50_ms']}ms |")
    (out / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nresultados → {out}")


if __name__ == "__main__":
    main()
