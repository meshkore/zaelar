"""rem_synth_bench.py — bench del modelo de SÍNTESIS del sueño REM (V2-056 · ronda 2026-08-09).

Pasa a cada candidato la tarea REAL (`nucleo/memllm.synthesize_concept_groups`, mismo prompt/parseo que usa el
sueño) sobre 8 grupos-fixture con hechos conocidos, 3 pasadas, y puntúa MECÁNICAMENTE.

**Aquí manda la CALIDAD, no el precio — al revés que en el CORAZÓN** (§12.3). Motivo estructural, no opinión:
`memory/rem.py` manda TODOS los grupos en **UNA sola llamada** (`memllm.synthesize_concept_groups`), con
`MAX_GROUPS=8` grupos × `pills[:12]` píldoras, **una vez al día** (`rem_every_hours=24`). O sea ~365 llamadas al
año por usuario con la entrada ACOTADA por diseño: **el coste NO escala con el tamaño de la memoria**. Un modelo
10× más caro sigue costando céntimos al año, mientras que un insight malo contamina la memoria de largo plazo
(se escribe con `slot=insight:<concepto>`, que el retriever puede devolver como si fuera un hecho del operador).
El $/sueño se reporta igualmente, para que la decisión sea informada y no un acto de fe.

SEIS ejes:
  1. VALIDEZ        — devuelve un item por grupo, bien formado.
  2. CLAVES         — nombres propios / cifras / fechas SOBREVIVEN a la síntesis (regla anti-T181: generalizar
                      «tiene dos hijos» donde ponía «Pau y Nil» destruye el dato).
  3. FORMA          — castellano (regla monolingüe), ≤260 chars, y NO copiar una píldora verbatim (es síntesis,
                      no resumen-lista).
  4. DISCIPLINA DE NULL — un grupo FLOJO debe volver con `insight: null` (lo pide el prompt). Inventar un insight
                      de tres trivialidades es peor que no dar ninguno. El bench viejo NO medía esto.
  5. NO-INVENCIÓN   — el insight no puede afirmar nada que NO esté en las píldoras (lista de términos prohibidos
                      por grupo, plausibles pero ausentes). Es el fallo MÁS caro: una alucinación consolidada
                      entra en la memoria durable con apariencia de hecho.
  6. $/SUEÑO y $/AÑO — con tokens REALES (`memllm.last_usage()`) × tarifa publicada (`prices.json`).

Uso: PYTHONPATH=. ./.venv/bin/python tests/memory/e2e/bot/rem_synth_bench.py [--models a,b] [--runs 3] [--preflight]
Veredictos → zaelar-model-benchmarks.md §12.4.
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

# Candidatos COMERCIALES de API. Como el coste es despreciable (1 llamada/día), el barrido incluye modelos
# POTENTES y RAZONADORES que en el CORAZÓN quedaron descartados por precio o por ensuciar descartes — aquí no
# hay descartes que ensuciar y sí una tarea de abstracción, que es donde un razonador podría aportar de verdad.
CANDIDATES: dict[str, tuple[str, str]] = {
    "gpt-4.1-mini":          (AIML, "openai/gpt-4.1-mini"),        # TITULAR actual (heredado de §12.2)
    "deepseek-v4-flash":     (AIML, "deepseek/deepseek-v4-flash"),  # empataba al titular en §12.2; el del CORAZÓN
    "deepseek-v4-pro":       (AIML, "deepseek/deepseek-v4-pro"),    # el DeepSeek POTENTE
    "deepseek-thinking":     (AIML, "deepseek/deepseek-thinking-v3.2-exp"),   # razonador DeepSeek
    "deepseek-reasoner":     (AIML, "deepseek/deepseek-reasoner"),
    "claude-haiku-4.5":      (AIML, "anthropic/claude-haiku-4.5"),
    "gemini-2.5-flash":      (AIML, "google/gemini-2.5-flash"),     # 50% en §12.2 — control
    "gemini-2.5-pro":        (AIML, "google/gemini-2.5-pro"),
    "gpt-5-mini":            (AIML, "openai/gpt-5-mini"),           # razonador
    "gpt-4.1":               (AIML, "openai/gpt-4.1"),
    "kimi-k2-6":             (AIML, "moonshot/kimi-k2-6"),
    "glm-4.7":               (AIML, "zhipu/glm-4.7"),
    "grok-4-fast-nonreason": (AIML, "x-ai/grok-4-fast-non-reasoning"),
    "gpt-4.1-mini@openai":   (OPENAI, "gpt-4.1-mini"),              # el camino que tenía antes del 2026-08-09
}

PRICES: dict[str, tuple[float, float]] = {}

# Grupos-fixture. `keys` = datos que DEBEN sobrevivir; `forbidden` = términos plausibles pero AUSENTES de las
# píldoras (si aparecen, el modelo se lo ha inventado); `want_null` = grupo flojo que NO merece insight.
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
    # NUEVO — EVOLUCIÓN/contradicción: el insight debe reflejar el estado ACTUAL, no promediar ni contradecirse.
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
    # NUEVO — CIFRAS y FECHAS densas (anti-T181 duro).
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
    # NUEVO — GRUPO GRANDE (12 píldoras, el tope real de `pills[:12]`): no debe perder los datos clave.
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
    # NUEVO — MULTILINGÜE: píldoras en otro idioma, el insight SIEMPRE en castellano (regla monolingüe).
    {"concept": "estudios", "want_null": False,
     "pills": [
         "Le interesa cada vez más la arquitectura.",
         "He is reading about fire-safe building design.",
         "Vol estudiar arquitectura de manera seriosa.",
         "Se apuntó a un curso online de estructuras en enero.",
     ],
     "keys": [["arquitectura"]],
     "forbidden": ["medicina", "derecho", "máster en harvard"]},
    # NUEVO — DISCIPLINA DE NULL: trivialidades sin patrón. El prompt PIDE insight null aquí.
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
    """Devuelve (puntos por eje, notas). Cada eje se agrega por separado (no se funden en un %)."""
    ax = {k: [0, 0] for k in ("validez", "claves", "forma", "null", "no_invencion")}   # [got, total]
    notes: list[str] = []
    by_c = {r["concept"]: r.get("insight") for r in results}
    for g in GROUPS_SPEC:
        c = g["concept"]
        ins = by_c.get(c) or ""
        n = _norm(ins)
        if g["want_null"]:
            ax["null"][1] += 1
            if not ins:
                ax["null"][0] += 1
            else:
                notes.append(f"{c}: DEBÍA ser null y sintetizó → «{ins[:90]}»")
            # un grupo que debía ser null no puntúa en los demás ejes, pero SÍ en no-invención si habló
            if ins:
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
        # claves
        for grp in g["keys"]:
            ax["claves"][1] += 1
            if any(_norm(k) in n for k in grp):
                ax["claves"][0] += 1
            else:
                notes.append(f"{c}: PERDIÓ la clave {grp[0]!r}")
        # forma
        ax["forma"][1] += 1
        es_ok = any(h in " " + n for h in _ES_HINTS)
        brief_ok = len(ins) <= 260
        not_verbatim = not any(_norm(p) == n for p in g["pills"])
        if es_ok and brief_ok and not_verbatim:
            ax["forma"][0] += 1
        else:
            why = [w for w, ok in (("no-es", es_ok), ("largo", brief_ok), ("verbatim", not_verbatim)) if not ok]
            notes.append(f"{c}: FORMA {why} ({len(ins)} chars) «{ins[:90]}»")
        # no-invención
        ax["no_invencion"][1] += 1
        bad = [f for f in g["forbidden"] if _norm(f) in n]
        ax["no_invencion"][0] += 0 if bad else 1
        if bad:
            notes.append(f"{c}: INVENTÓ {bad} → «{ins[:90]}»")
    return ax, notes


def _pct(pair) -> float:
    return round(100 * pair[0] / pair[1], 1) if pair[1] else 100.0


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
        # media de los CINCO ejes de calidad — resumen, no sustituto de mirarlos por separado
        row["calidad_pct"] = round(statistics.mean(
            [row["validez"], row["claves"], row["forma"], row["null"], row["no_invencion"]]), 1)
        out_rows.append(row)
        print(f"   calidad={row['calidad_pct']}%  (val={row['validez']} claves={row['claves']} "
              f"forma={row['forma']} null={row['null']} no-inv={row['no_invencion']})  "
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
        lines.append(f"| {r['model']} | **{r['calidad_pct']}%** | {r['validez']}% | {r['claves']}% | "
                     f"{r['forma']}% | {r['null']}% | {r['no_invencion']}% | {cost} | {r['p50_ms']}ms |")
    (out / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nresultados → {out}")


if __name__ == "__main__":
    main()
