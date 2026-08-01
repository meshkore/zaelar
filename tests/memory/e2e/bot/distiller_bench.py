"""distiller_bench.py — bench de WRITE-COMPLETENESS + PRECISIÓN del CORAZÓN por modelo (V2-056, 2026-07-20).

Elige el modelo del destilador (`config §memory.mem_processor_*`) CON DATOS, no especulando (regla del operador:
"más que especular, PRUEBAS", benchmarks §9). Pasa a cada candidato los 16 casos duros por el CAMINO REAL
(`mem_processor.process`, mismo prompt/parseo/contrato v2) y puntúa:

  - KEEP (12 casos): % de HECHOS ESPERADOS capturados en los átomos (substring acento-insensible sobre
    text+slot+value). Cubre: multi-hecho médico, precio, mudanza (slot+change), corrección de identidad,
    compromiso con fecha, rutina, reversión, observación, nombre propio en PARRAFADA (T181), telegráfico,
    inglés→es y catalán→es (monolingüe: SIEMPRE castellano), familia con nombres.
  - DISCARD (4 casos): pregunta al asistente, petición efímera, ack, comando — puntúan SOLO si el modelo
    devuelve [] (la precisión importa tanto como la completitud, V2-033).
  - Penalización de IDIOMA: átomo durable no-castellano = -0.5 (regla monolingüe).

Uso:  PYTHONPATH=. ./.venv/bin/python tests/memory/e2e/bot/distiller_bench.py [--models a,b] [--runs 1]
Requiere .env (OPENAI_API_KEY / AIMLAPI_KEY) y, para el candidato local, Ollama arriba.
Resultados → tests/memory/e2e/bot/resultados/<fecha>-distiller-bench/report.md (+ .json). Veredictos → benchmarks §12.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
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

from nucleo import mem_processor as mp  # noqa: E402

# ── candidatos (url, model, key-env). NO-razonadores salvo nota; el destilador va off-hot-path pero un
# razonador multiplica coste/latencia sin evidencia de mejora en extracción. ─────────────────────────────
AIMLAPI = "https://api.aimlapi.com/v1"
CANDIDATES: dict[str, tuple[str, str]] = {
    "gpt-4.1-mini":      ("https://api.openai.com/v1", "gpt-4.1-mini"),            # titular (4/4 el 07-17)
    "claude-haiku-4.5":  (AIMLAPI, "anthropic/claude-haiku-4.5"),                   # mejor FC del catálogo (§2)
    "gemini-2.5-flash":  (AIMLAPI, "google/gemini-2.5-flash"),                      # 12/12 routing FAST (§11)
    "deepseek-v4-flash": (AIMLAPI, "deepseek/deepseek-v4-flash"),                   # nunca probado con endpoint OK (§9.2)
    "qwen3.5-flash":     (AIMLAPI, "alibaba/qwen3.5-flash"),                        # familia qwen destila bien (7b 12/12)
    "qwen2.5:7b-local":  ("http://localhost:11434/v1", "qwen2.5:7b-instruct"),      # 12/12 histórico (2026-07-14), LOCAL
}

STATE = {"operator_name": "Ricart", "location": "Soria", "language": "es"}

# (id, texto, esperados [grupo de alternativas por hecho], must_discard)
CASES: list[tuple[str, str, list[list[str]], bool]] = [
    ("medico-multi", "Soy alérgico a la penicilina y también al marisco, que no se te olvide",
     [["penicilina"], ["marisco"]], False),
    ("compra-precio", "Me he comprado una bici eléctrica para ir al trabajo, me costó 1.800 euros",
     [["bici"], ["1800", "1.800"]], False),
    ("mudanza", "Oye, al final nos hemos mudado a Valencia con toda la familia",
     [["valencia"]], False),
    ("correccion", "Que no, que no me llamo Ricardo, me llamo Ricart",
     [["ricart"]], False),
    ("compromiso", "Mi jefa Marta me pidió el informe trimestral para el miércoles que viene",
     [["informe"], ["miércoles", "miercoles"], ["marta"]], False),
    ("rutina", "Todos los lunes y jueves voy al gimnasio a las siete de la mañana",
     [["lunes"], ["jueves"], ["gimnasio"]], False),
    ("reversion", "Por cierto, ya no bebo café desde enero, lo dejé del todo",
     [["café", "cafe"]], False),
    ("observacion", "He notado que rindo muchísimo mejor por las mañanas que por las tardes",
     [["mañana", "manana"]], False),
    ("parrafada-t181", "Pues nada, que ayer estuvimos cenando con los de siempre y salió el tema de los conciertos, "
     "que si los festivales ya no son lo que eran, bla bla, y total que al final he pillado entradas para el "
     "concierto de Muse en Bilbao el 12 de septiembre, ya te contaré qué tal",
     [["muse"], ["bilbao"], ["12", "septiembre"]], False),
    ("telegrafico", "Presupuesto vacaciones: 3000 euros máximo",
     [["3000", "3.000"], ["vacaciones"]], False),
    ("ingles", "By the way, my daughter Emma turns 8 next month",
     [["emma"], ["8", "ocho"]], False),
    ("familia", "En casa somos cinco: mi mujer Marta, los gemelos Pau y Nil, y mi madre que vive con nosotros",
     [["marta"], ["pau"], ["nil"], ["cinco", "5"]], False),
    # DISCARD — la precisión (V2-033) puntúa igual que la completitud
    ("q-asistente", "¿Qué tiempo va a hacer mañana en Soria?", [], True),
    ("efimera", "Ahora no me enseñes nada más, luego seguimos", [], True),
    ("ack", "Vale, perfecto, muchas gracias", [], True),
    ("comando", "Pon música de los ochenta y sube un poco el volumen", [], True),
]


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(c) != "Mn")


def _atom_blob(a: dict) -> str:
    return _norm(" ".join(str(a.get(k) or "") for k in ("text", "slot", "value")))


_ES_HINTS = ("el ", "la ", "los ", "se ", "su ", "de ", "que ", "es ", "tiene", "prefiere", "opera")


def _looks_spanish(text: str) -> bool:
    t = " " + _norm(text) + " "
    return any(h in t for h in _ES_HINTS)


async def run_model(name: str, url: str, model: str, runs: int) -> dict:
    # override del routing del procesador (mismo camino real, otro modelo)
    mp._config_url = lambda: url                     # type: ignore[assignment]
    mp._model = lambda: model                        # type: ignore[assignment]
    detail, lat = [], []
    score = total = 0.0
    for cid, text, expected, must_discard in CASES:
        t0 = time.time()
        atoms = await mp.process(text, state=STATE)
        ms = round((time.time() - t0) * 1000)
        lat.append(ms)
        atoms = atoms if isinstance(atoms, list) else None
        if must_discard:
            total += 1
            ok = atoms is not None and len(atoms) == 0
            score += 1 if ok else 0
            detail.append({"case": cid, "ok": ok, "ms": ms,
                           "got": [a.get("text") for a in (atoms or [])] or ("<None=fallo>" if atoms is None else "[]")})
            continue
        hits = 0
        blobs = [_atom_blob(a) for a in (atoms or [])]
        for group in expected:
            if any(any(_norm(alt) in b for b in blobs) for alt in group):
                hits += 1
        lang_pen = sum(0.5 for a in (atoms or [])
                       if a.get("dest") in ("long", "mid") and a.get("text") and not _looks_spanish(a["text"]))
        total += len(expected)
        score += max(0.0, hits - lang_pen)
        detail.append({"case": cid, "hits": f"{hits}/{len(expected)}", "lang_pen": lang_pen, "ms": ms,
                       "got": [a.get("text") for a in (atoms or [])] or "<None=fallo>"})
    return {"model": name, "endpoint": url, "score": round(score, 1), "total": total,
            "pct": round(100 * score / total, 1), "p50_ms": int(statistics.median(lat)), "detail": detail}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=",".join(CANDIDATES))
    ap.add_argument("--runs", type=int, default=1)
    args = ap.parse_args()

    results = []
    for name in [m.strip() for m in args.models.split(",") if m.strip()]:
        if name not in CANDIDATES:
            print(f"?? candidato desconocido: {name}", file=sys.stderr)
            continue
        url, model = CANDIDATES[name]
        print(f"→ {name} ({model} @ {url.split('//')[1].split('/')[0]}) …", flush=True)
        try:
            r = await run_model(name, url, model, args.runs)
        except Exception as e:  # noqa: BLE001
            r = {"model": name, "error": str(e)[:200]}
        results.append(r)
        print(f"   {r.get('pct', '—')}%  p50={r.get('p50_ms', '—')}ms")

    out = Path(__file__).parent / "resultados" / f"{time.strftime('%Y%m%d')}-distiller-bench"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    ok = [r for r in results if "pct" in r]
    lines = ["# Bench del DESTILADOR (write-completeness + precisión) — " + time.strftime("%Y-%m-%d %H:%M"),
             "", "| modelo | score | % | p50 ms |", "|---|---|---|---|"]
    for r in sorted(ok, key=lambda x: -x["pct"]):
        lines.append(f"| {r['model']} | {r['score']}/{r['total']} | {r['pct']}% | {r['p50_ms']} |")
    for r in results:
        if "error" in r:
            lines.append(f"| {r['model']} | ERROR | — | — | {r['error']}")
    (out / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nresultados → {out}")


if __name__ == "__main__":
    asyncio.run(main())
