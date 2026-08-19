"""distiller_bench.py — bench de CALIDAD-vs-PRECIO del CORAZÓN de escritura, por modelo (V2-056 · ronda 2026-08-09).

Elige el modelo del destilador (`config §memory.mem_processor_*`) CON DATOS, no especulando (regla del operador:
"más que especular, PRUEBAS", benchmarks §9). Pasa a cada candidato los MISMOS 34 casos por el CAMINO REAL
(`mem_processor.process`, mismo prompt/parseo/contrato v2).

**El eje es calidad-vs-PRECIO, no velocidad.** Escribir va OFF-HOT-PATH (cola async, fire-and-forget): la latencia
del destilador NO la paga el turno de voz — la lectura, que sí la paga, no usa ningún LLM (retriever sqlite-vec +
FTS5 + reranker). Por eso `p50` se reporta como dato de cordura y NO puntúa: un modelo lento y barato es
perfectamente válido aquí. Lo que NO es tolerable es perder un hecho durable (write-completeness es la palanca nº1
del recall, V2-031: la mayoría de los "no recuperados" ni siquiera están GUARDADOS).

CUATRO ejes SEPARADOS (antes iban fundidos en un solo %, que escondía de qué flojeaba un modelo):

  1. WRITE-COMPLETENESS (24 casos) — % de HECHOS ESPERADOS capturados en los átomos (substring acento-insensible
     sobre text+slot+value). Multi-hecho médico, precio, mudanza, corrección de identidad, compromisos propios y
     ajenos, rutina, reversión, observación, nombre propio en PARRAFADA (T181), telegráfico, EN→es, CA→es, familia
     con nombres, secreto que el operador PIDE guardar, importes, garble de STT con dato bueno, evento médico.
  2. PRECISIÓN / no-pollution (10 casos) — % de DESCARTES limpios: preguntas al asistente, órdenes, acks, ruido de
     STT, meta-preguntas sobre la propia memoria. Puntúan SOLO si el modelo devuelve []. NO se penalizan píldoras
     EXTRA en los casos KEEP: el prompt PIDE inferir intereses/intenciones (kind pref/intent), así que contarlas
     como ruido sería medir justo al revés de lo que se le pide al modelo.
  3. CAPA/SLOT (16 comprobaciones) — el metadato, que es lo que hace que la píldora se pueda corregir y recuperar:
     `dest` correcto (state/short/long), `slot` canónico correcto Y —el error caro— `slot=None` en los hechos
     ADITIVOS (una alergia NO es `operator.diet`: si lo fuera, un cambio de dieta borraría la alergia), `change`
     (update/correction) y `kind` (intent) donde toca.
  4. $/1k TURNOS — con tokens REALES del proveedor (`mem_processor.last_usage()`, capturado por el propio módulo
     desde 2026-08-09) × tarifa publicada. NO estimados: el prompt del CORAZÓN son ~3.700 tokens de input FIJOS
     (system + 8 pares de few-shot), así que el coste lo domina el input y una estimación por chars se desvía.

  + Penalización de IDIOMA: átomo durable no-castellano = -0.5 sobre completeness (regla monolingüe: la memoria vive
    en el idioma del operador, se TRADUCE lo que venga en otro y nunca se descarta un durable por su idioma).

Uso:  PYTHONPATH=. ./.venv/bin/python tests/memory/e2e/bot/distiller_bench.py [--models a,b] [--runs 1] [--preflight]
      --preflight   solo comprueba que cada candidato responde (1 llamada corta), sin correr el corpus.
Requiere .env / .meshkore/credentials/zaelar.env con las keys de los endpoints a barrer.
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

# El cap de concurrencia del CORAZÓN (def 1) existe para NO apilar en la GPU Metal cuando corre en Ollama local;
# contra una API remota no aplica y serializar 34 casos × N modelos costaría media hora de reloj sin ganar nada.
# Se sube ANTES de importar el módulo (el semáforo se crea al importar). No cambia el código de producción.
os.environ.setdefault("MEM_PROCESSOR_CONCURRENCY", "6")
os.environ.setdefault("MEM_PROCESSOR_QUEUE_MAX", "64")
os.environ.setdefault("MEM_PROCESSOR_QUEUE_WAIT", "600")
os.environ.setdefault("MEM_PROCESSOR_TIMEOUT", "90")     # timeout de CORDURA, no de latencia (ver docstring)
os.environ.setdefault("MEM_PROCESSOR_RETRIES", "1")
# Este banco mide MODELOS, así que corre SIN failover: con la cadena puesta (norma de proveedores 2026-08-19) un
# candidato que falla se releva al siguiente y su fila reporta el trabajo de OTRO modelo como si fuera suyo.
# Medido el mismo día: `qwen3.6-27b@ollama` salió «OK 143000ms, 2 píldoras» y esas píldoras eran de DeepSeek.
os.environ["MEM_PROCESSOR_PIN_TITULAR"] = "1"

from nucleo import mem_processor as mp  # noqa: E402

# ── candidatos ──────────────────────────────────────────────────────────────────────────────────────────────
# El broker AIMLAPI es el endpoint que la nube YA usa (fly.accounts.toml + provisioner), así que un ganador que viva
# ahí no exige endpoint ni secret nuevos; los DIRECTOS se miden para saber cuánto se paga por el hop del broker.
#
# ⚠️ **LA VÍA LOCAL VUELVE (2026-08-19, decisión del operador)**, y esto es una REVERSIÓN explícita, no un despiste:
# el 2026-08-09 se retiró («UN solo modelo que sirva igual en self-host y en cloud», porque obligaba a dos ganadores
# distintos). La norma nueva acepta justamente eso: en LOCAL, Ollama de titular si está disponible, con DeepSeek V4
# Flash directo de failover. Así que ahora hay DOS ganadores por diseño y hacen falta DOS columnas de resultados —
# **un modelo local y uno de nube NO se pueden comparar por el ranking global**: el local puntúa gratis en $/1k y
# paga en latencia y en GPU compartida con STT/TTS, el de nube al contrario. Por eso el informe se guarda POR
# MODELO (petición del operador: «los tests por modelos son importantes»), y el veredicto de un local se lee contra
# otros locales, nunca contra la tabla de nube.
AIML = "https://api.aimlapi.com/v1"
OLLAMA = "http://localhost:11434/v1"
OPENAI = "https://api.openai.com/v1"
GROQ = "https://api.groq.com/openai/v1"
XAI = "https://api.x.ai/v1"
ZAI = "https://api.z.ai/api/paas/v4"
MISTRAL = "https://api.mistral.ai/v1"

CANDIDATES: dict[str, tuple[str, str]] = {
    # titular actual, por los DOS caminos (self-host apunta a OpenAI directo; la nube al broker)
    "gpt-4.1-mini@openai":      (OPENAI, "gpt-4.1-mini"),
    "gpt-4.1-mini@aimlapi":     (AIML, "openai/gpt-4.1-mini"),
    # OpenAI más baratos
    "gpt-4.1-nano":             (AIML, "openai/gpt-4.1-nano"),
    "gpt-5-nano":               (AIML, "openai/gpt-5-nano"),
    "gpt-5-mini":               (AIML, "openai/gpt-5-mini"),
    "gpt-4o-mini":              (OPENAI, "gpt-4o-mini"),          # CONTROL negativo: §9.2 lo vio comerse la alergia
    # OJO al medir por OpenAI DIRECTO: esa cuenta va muy limitada de tasa — con 6 llamadas en vuelo devuelve
    # HTTP 429 en ~1 de cada 5 (21 muertas de 102 en la Fase 2) y hunde el score por una razón que NO es el
    # modelo. Por el broker sale limpio, y además es el camino que usa la nube de verdad.
    "gpt-4o-mini@aimlapi":      (AIML, "openai/gpt-4o-mini"),
    # el tramo barato del broker
    "deepseek-v4-flash":        (AIML, "deepseek/deepseek-v4-flash"),
    "deepseek-chat":            (AIML, "deepseek/deepseek-chat"),
    "gemini-2.5-flash":         (AIML, "google/gemini-2.5-flash"),
    "gemini-2.5-flash-lite":    (AIML, "google/gemini-2.5-flash-lite"),
    "kimi-k2-6":                (AIML, "moonshot/kimi-k2-6"),
    "grok-4-fast-nonreason":    (AIML, "x-ai/grok-4-fast-non-reasoning"),
    "glm-4.7":                  (AIML, "zhipu/glm-4.7"),
    "ministral-8b":             (AIML, "mistralai/ministral-8b-2512"),
    "llama-3.3-70b":            (AIML, "meta-llama/llama-3.3-70b-versatile"),
    "qwen2.5-7b-turbo":         (AIML, "Qwen/Qwen2.5-7B-Instruct-Turbo"),
    # DIRECTOS (sin el hop del broker; keys propias)
    "llama-3.3-70b@groq":       (GROQ, "llama-3.3-70b-versatile"),
    "grok-4.20-nonreason@xai":  (XAI, "grok-4.20-0309-non-reasoning"),
    "glm-4.7@zai":              (ZAI, "glm-4.7"),
    "glm-4.7-flash@zai":        (ZAI, "glm-4.7-flash"),
    "ministral-8b@mistral":     (MISTRAL, "ministral-8b-latest"),
    # LOCALES (Ollama). No llevan key y su $/1k es 0 — un cero LEGÍTIMO, no un hueco: el coste marginal de un
    # modelo local es cero de verdad, y lo que se paga está en las otras dos columnas (latencia y GPU). Un
    # candidato que no esté `pull`eado en la máquina se salta con un aviso en vez de puntuar 0 —- un modelo ausente
    # no es un modelo malo, y contarlo como tal ensuciaría el informe de quien no lo tenga.
    "qwen3.6-27b@ollama":       (OLLAMA, "qwen3.6:27b-mlx"),
    "qwen2.5-7b@ollama":        (OLLAMA, "qwen2.5:7b-instruct"),
    "qwen2.5-14b@ollama":       (OLLAMA, "qwen2.5:14b-instruct"),
}

# $ por 1M tokens (input, output). Tarifa PUBLICADA del proveedor que sirve ese id — verificada por web el
# 2026-08-09 (ver §12.3 del doc de benchmarks). RE-VERIFICAR periódicamente: los precios cambian sin aviso.
# Se usan aquí y, para el ganador, se replican en `nucleo/energy_meter.py`.
PRICES: dict[str, tuple[float, float]] = {}   # se rellena desde prices.json si existe (ver _load_prices)

STATE = {"operator_name": "Ricart", "location": "Soria", "language": "es"}

# ── corpus ──────────────────────────────────────────────────────────────────────────────────────────────────
# Cada caso: id, texto, hechos esperados (lista de GRUPOS de alternativas — un grupo = un hecho, capta si aparece
# CUALQUIERA de sus formas), must_discard, y `layer` = comprobaciones de metadato (eje 3). Claves de `layer`:
#   dest_all   — TODOS los átomos deben tener este dest
#   dest_any   — AL MENOS un átomo con este dest
#   slot       — (substring del hecho, slot esperado) — `None` = el hecho NO debe llevar slot (regla aditiva)
#   change_any — al menos un átomo con esta señal de cambio
#   kind_any   — al menos un átomo de este kind
CASES: list[dict] = [
    # ── KEEP · write-completeness ───────────────────────────────────────────────────────────────────────────
    {"id": "medico-multi", "text": "Soy alérgico a la penicilina y también al marisco, que no se te olvide",
     "expect": [["penicilina"], ["marisco"]],
     # el error CARO: una alergia es ADITIVA (se puede ser alérgico a varias cosas) → slot=None. Si fuera
     # operator.diet, un cambio de dieta invalidaría la alergia.
     "layer": {"slot": [("penicilina", None), ("marisco", None)], "dest_any": "long"}},
    {"id": "compra-precio", "text": "Me he comprado una bici eléctrica para ir al trabajo, me costó 1.800 euros",
     "expect": [["bici"], ["1800", "1.800"]]},
    {"id": "mudanza", "text": "Oye, al final nos hemos mudado a Valencia con toda la familia",
     "expect": [["valencia"]],
     "layer": {"dest_any": "state", "slot": [("valencia", "operator.location")], "change_any": "update"}},
    {"id": "correccion", "text": "Que no, que no me llamo Ricardo, me llamo Ricart",
     "expect": [["ricart"]],
     "layer": {"slot": [("ricart", "operator.name")], "change_any": "correction"}},
    {"id": "compromiso", "text": "Mi jefa Marta me pidió el informe trimestral para el miércoles que viene",
     "expect": [["informe"], ["miércoles", "miercoles"], ["marta"]]},
    {"id": "rutina", "text": "Todos los lunes y jueves voy al gimnasio a las siete de la mañana",
     "expect": [["lunes"], ["jueves"], ["gimnasio"]]},
    {"id": "reversion", "text": "Por cierto, ya no bebo café desde enero, lo dejé del todo",
     "expect": [["café", "cafe"]]},
    {"id": "observacion", "text": "He notado que rindo muchísimo mejor por las mañanas que por las tardes",
     "expect": [["mañana", "manana"]]},
    {"id": "parrafada-t181",
     "text": "Pues nada, que ayer estuvimos cenando con los de siempre y salió el tema de los conciertos, "
             "que si los festivales ya no son lo que eran, bla bla, y total que al final he pillado entradas "
             "para el concierto de Muse en Bilbao el 12 de septiembre, ya te contaré qué tal",
     "expect": [["muse"], ["bilbao"], ["12", "septiembre"]],
     "layer": {"dest_any": "long"}},
    {"id": "telegrafico", "text": "Presupuesto vacaciones: 3000 euros máximo",
     "expect": [["3000", "3.000"], ["vacaciones"]]},
    {"id": "ingles", "text": "By the way, my daughter Emma turns 8 next month",
     "expect": [["emma"], ["8", "ocho"]]},
    {"id": "familia",
     "text": "En casa somos cinco: mi mujer Marta, los gemelos Pau y Nil, y mi madre que vive con nosotros",
     "expect": [["marta"], ["pau"], ["nil"], ["cinco", "5"]],
     "layer": {"slot": [("marta", None)]}},
    # ── KEEP nuevos (ronda 2026-08-09) — los que de verdad separan modelos ──────────────────────────────────
    {"id": "alergia-ingles", "text": "I'm severely allergic to shellfish, please don't ever forget that",
     # regla monolingüe: el dato NO se descarta por venir en inglés, se TRADUCE a castellano
     "expect": [["marisco"]],
     "layer": {"slot": [("marisco", None)]}},
    {"id": "catalan-mudanza", "text": "Doncs res, que ara visc a Girona i treballo de fuster",
     "expect": [["girona"], ["fuster", "carpinter", "ebanist"]],
     "layer": {"slot": [("girona", "operator.location")]}},
    {"id": "secreto-pedido",
     "text": "Apúntate esto que siempre lo pierdo: la contraseña del router es Zx9tormenta",
     # el prompt es explícito: un secreto que el operador PIDE recordar SÍ se guarda (es su memoria personal)
     "expect": [["zx9tormenta", "zx9"]]},
    {"id": "compromiso-ajeno", "text": "Mi madre me ha pedido que la llame el domingo por la tarde",
     "expect": [["madre"], ["domingo"]]},
    {"id": "correccion-fecha",
     "text": "Oye, corrijo: la reunión con el notario no es el martes, es el jueves a las diez",
     "expect": [["notario"], ["jueves"]]},
    {"id": "interes-intent", "text": "Estoy mirando cursos de buceo para el año que viene",
     "expect": [["buceo"]],
     # el prompt pide INFERIR interés + intención como píldoras extra
     "layer": {"kind_any": "intent"}},
    {"id": "cotidiano-short",
     "text": "Hoy he comido un bocadillo en el bar de abajo y estoy reventado, pero mañana ya estaré bien",
     "expect": [["bocadillo", "cansad", "revent", "comi"]],
     # cotidianeidad efímera: NO promocionar a durable ni fabricar un objetivo de "mañana estaré bien"
     "layer": {"dest_all": "short"}},
    {"id": "multi-profesional",
     "text": "Soy arquitecto, trabajo en un estudio en Bilbao y tengo dos hijas, Nora y Vega",
     "expect": [["arquitect"], ["bilbao"], ["nora"], ["vega"]],
     "layer": {"slot": [("arquitect", "operator.job")]}},
    {"id": "importe-hipoteca",
     "text": "Ya hemos firmado la hipoteca: 250.000 euros a 30 años con el Santander",
     "expect": [["250.000", "250000"], ["30"], ["santander"]]},
    {"id": "garble-identidad", "text": "me llamo eeeh… Ricart, Ricart con te al final, no Ricardo",
     "expect": [["ricart"]],
     "layer": {"slot": [("ricart", "operator.name")]}},
    {"id": "evento-medico", "text": "La semana pasada me operaron del menisco de la rodilla derecha",
     "expect": [["menisco"]],
     "layer": {"dest_any": "long"}},
    {"id": "reversion-laboral", "text": "Ya no trabajo en Telefónica, lo dejé en marzo",
     "expect": [["telefónica", "telefonica"]],
     "layer": {"change_any": "update"}},
    # ── DISCARD · precisión (no-pollution) ─────────────────────────────────────────────────────────────────
    {"id": "q-asistente", "text": "¿Qué tiempo va a hacer mañana en Soria?", "discard": True},
    {"id": "efimera", "text": "Ahora no me enseñes nada más, luego seguimos", "discard": True},
    {"id": "ack", "text": "Vale, perfecto, muchas gracias", "discard": True},
    {"id": "comando", "text": "Pon música de los ochenta y sube un poco el volumen", "discard": True},
    {"id": "saludo", "text": "Buenos días, ¿qué tal estás hoy?", "discard": True},
    {"id": "orden-widget", "text": "Abre el widget de la agenda y luego ciérralo", "discard": True},
    {"id": "meta-memoria", "text": "¿Te acuerdas de lo que te conté ayer?", "discard": True},
    {"id": "ruido-stt", "text": "eh… mmm… no, nada, espera… déjalo", "discard": True},
    {"id": "repeticion", "text": "¿Me lo puedes repetir, por favor?", "discard": True},
    {"id": "queja-asistente", "text": "No, eso no era lo que te he dicho, escucha mejor", "discard": True},
]


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(c) != "Mn")


def _atom_blob(a: dict) -> str:
    return _norm(" ".join(str(a.get(k) or "") for k in ("text", "slot", "value")))


_ES_HINTS = ("el ", "la ", "los ", "se ", "su ", "de ", "que ", "es ", "tiene", "prefiere", "opera")


def _looks_spanish(text: str) -> bool:
    t = " " + _norm(text) + " "
    return any(h in t for h in _ES_HINTS)


def _score_layer(case: dict, atoms: list[dict]) -> tuple[float, int, list[str]]:
    """Eje 3 — metadato (dest/slot/change/kind). Devuelve (aciertos, total, fallos legibles)."""
    exp = case.get("layer") or {}
    hits = total = 0
    misses: list[str] = []
    if not atoms:
        # sin átomos no hay metadato que juzgar; el fallo ya lo captura completeness (no se penaliza dos veces)
        n = len(exp.get("slot", [])) + sum(1 for k in ("dest_all", "dest_any", "change_any", "kind_any") if k in exp)
        return 0, n, [f"{case['id']}: sin átomos"]
    if "dest_all" in exp:
        total += 1
        if all((a.get("dest") or "") == exp["dest_all"] for a in atoms):
            hits += 1
        else:
            misses.append(f"{case['id']}: dest_all={exp['dest_all']} got={[a.get('dest') for a in atoms]}")
    if "dest_any" in exp:
        total += 1
        if any((a.get("dest") or "") == exp["dest_any"] for a in atoms):
            hits += 1
        else:
            misses.append(f"{case['id']}: dest_any={exp['dest_any']} got={[a.get('dest') for a in atoms]}")
    if "change_any" in exp:
        total += 1
        if any((a.get("change") or "") == exp["change_any"] for a in atoms):
            hits += 1
        else:
            misses.append(f"{case['id']}: change_any={exp['change_any']} got={[a.get('change') for a in atoms]}")
    if "kind_any" in exp:
        total += 1
        if any((a.get("kind") or "") == exp["kind_any"] for a in atoms):
            hits += 1
        else:
            misses.append(f"{case['id']}: kind_any={exp['kind_any']} got={[a.get('kind') for a in atoms]}")
    for needle, want_slot in exp.get("slot", []):
        total += 1
        owner = next((a for a in atoms if _norm(needle) in _atom_blob(a)), None)
        if owner is None:
            misses.append(f"{case['id']}: no hay átomo con «{needle}» para juzgar su slot")
            continue
        got = owner.get("slot") or None
        if got == want_slot:
            hits += 1
        else:
            misses.append(f"{case['id']}: slot de «{needle}» = {got!r}, esperado {want_slot!r}")
    return hits, total, misses


async def _one_case(case: dict, sem: asyncio.Semaphore) -> dict:
    async with sem:
        t0 = time.time()
        try:
            atoms = await mp.process(case["text"], state=STATE)
        except Exception as e:  # noqa: BLE001  — process() no debería lanzar, pero un candidato roto no tumba el barrido
            return {"case": case["id"], "error": f"{type(e).__name__}: {e}"[:160], "ms": 0, "atoms": None}
        return {"case": case["id"], "atoms": atoms if isinstance(atoms, list) else None,
                "ms": round((time.time() - t0) * 1000)}


async def run_model(name: str, url: str, model: str) -> dict:
    # override del routing del procesador (mismo camino real, otro modelo)
    mp._config_url = lambda: url                     # type: ignore[assignment]
    mp._model = lambda: model                        # type: ignore[assignment]

    # captura EXACTA del usage por llamada (last_usage() es un global y con concurrencia se pisaría)
    usages: list[dict] = []
    _orig_record = mp._record_usage

    def _capture(u):                                  # noqa: ANN001
        if isinstance(u, dict):
            usages.append({k: u.get(k) for k in ("prompt_tokens", "completion_tokens")})
        _orig_record(u)
    mp._record_usage = _capture                       # type: ignore[assignment]

    sem = asyncio.Semaphore(6)
    try:
        results = await asyncio.gather(*[_one_case(c, sem) for c in CASES])
    finally:
        mp._record_usage = _orig_record               # type: ignore[assignment]

    by_id = {r["case"]: r for r in results}
    comp_score = comp_total = 0.0
    prec_hits = prec_total = 0
    layer_hits = layer_total = 0
    lang_pen_total = 0.0
    dead = 0
    detail, misses = [], []
    for case in CASES:
        r = by_id[case["id"]]
        atoms = r.get("atoms")
        if atoms is None:
            dead += 1
        if case.get("discard"):
            prec_total += 1
            ok = atoms is not None and len(atoms) == 0
            prec_hits += 1 if ok else 0
            detail.append({"case": case["id"], "axis": "precision", "ok": ok, "ms": r["ms"],
                           "got": [a.get("text") for a in (atoms or [])] or
                                  ("<None=fallo del modelo>" if atoms is None else "[]")})
            if not ok:
                misses.append(f"{case['id']}: ensució con {[a.get('text') for a in (atoms or [])] or 'None'}")
            continue
        expected = case["expect"]
        blobs = [_atom_blob(a) for a in (atoms or [])]
        hits = sum(1 for group in expected if any(any(_norm(alt) in b for b in blobs) for alt in group))
        lang_pen = sum(0.5 for a in (atoms or [])
                       if a.get("dest") in ("long", "mid") and a.get("text") and not _looks_spanish(a["text"]))
        lang_pen_total += lang_pen
        comp_total += len(expected)
        comp_score += max(0.0, hits - lang_pen)
        lh, lt, lm = _score_layer(case, atoms or [])
        layer_hits += lh
        layer_total += lt
        misses.extend(lm)
        if hits < len(expected):
            missing = [g[0] for g in expected if not any(any(_norm(alt) in b for b in blobs) for alt in g)]
            misses.append(f"{case['id']}: PERDIÓ {missing}")
        detail.append({"case": case["id"], "axis": "completeness", "hits": f"{hits}/{len(expected)}",
                       "lang_pen": lang_pen, "layer": f"{lh}/{lt}", "ms": r["ms"],
                       "got": [a.get("text") for a in (atoms or [])] or "<None=fallo del modelo>"})

    lat = [r["ms"] for r in results if r["ms"]]
    in_tok = [u.get("prompt_tokens") or 0 for u in usages]
    out_tok = [u.get("completion_tokens") or 0 for u in usages]
    avg_in = round(statistics.mean(in_tok)) if in_tok else 0
    avg_out = round(statistics.mean(out_tok)) if out_tok else 0
    return {
        "model": name, "endpoint": url, "model_id": model,
        "completeness_pct": round(100 * comp_score / comp_total, 1) if comp_total else 0.0,
        "completeness": f"{round(comp_score, 1)}/{round(comp_total)}",
        "precision_pct": round(100 * prec_hits / prec_total, 1) if prec_total else 0.0,
        "precision": f"{prec_hits}/{prec_total}",
        "layer_pct": round(100 * layer_hits / layer_total, 1) if layer_total else 0.0,
        "layer": f"{layer_hits}/{layer_total}",
        "lang_pen": lang_pen_total, "dead_calls": dead,
        "p50_ms": int(statistics.median(lat)) if lat else 0,
        "avg_in_tok": avg_in, "avg_out_tok": avg_out, "usage_calls": len(usages),
        "detail": detail, "misses": misses,
    }


def _cost_per_1k(res: dict) -> float | None:
    """$ por 1.000 turnos destilados, con tokens MEDIDOS × tarifa publicada. None si no hay tarifa cargada."""
    rate = PRICES.get(res["model"])
    if not rate or not res.get("avg_in_tok"):
        return None
    r_in, r_out = rate
    return round(1000 * ((res["avg_in_tok"] / 1e6) * r_in + (res["avg_out_tok"] / 1e6) * r_out), 3)


def _load_prices() -> None:
    """Tarifas desde `prices.json` (junto a este script) — se mantienen FUERA del código para poder re-verificarlas
    por web sin tocar el arnés (norma del repo: los precios cambian sin aviso, se re-verifican periódicamente)."""
    p = Path(__file__).parent / "prices.json"
    if p.exists():
        PRICES.update({k: tuple(v) for k, v in json.loads(p.read_text()).items()})


async def _preflight(names: list[str]) -> None:
    """1 llamada CORTA por candidato: separa «el modelo no vale» de «el id/endpoint/contrato no responde»."""
    for name in names:
        url, model = CANDIDATES[name]
        mp._config_url = lambda u=url: u              # type: ignore[assignment]
        mp._model = lambda m=model: m                 # type: ignore[assignment]
        t0 = time.time()
        atoms = await mp.process("Me llamo Marta y vivo en Lugo.", state=STATE)
        ms = round((time.time() - t0) * 1000)
        state = "OK" if isinstance(atoms, list) else "FALLO"
        extra = f" ({len(atoms)} píldoras, in={mp.last_usage().get('prompt_tokens')})" if isinstance(atoms, list) else \
                f" — {mp.status()['last_error'][:110]}"
        print(f"  {state:5s} {name:26s} {ms:6d}ms{extra}", flush=True)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=",".join(CANDIDATES))
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    _load_prices()

    names = [m.strip() for m in args.models.split(",") if m.strip()]
    unknown = [n for n in names if n not in CANDIDATES]
    for n in unknown:
        print(f"?? candidato desconocido: {n}", file=sys.stderr)
    names = [n for n in names if n in CANDIDATES]

    # Un candidato LOCAL que no está `pull`eado en esta máquina se SALTA con aviso, nunca puntúa 0: un modelo
    # ausente no es un modelo malo, y dejarlo correr le daría un 0% de completeness que ensucia el informe de
    # cualquiera que no lo tenga instalado. Reutiliza la MISMA sonda que usa producción para decidir si el titular
    # local está disponible (`nucleo/memllm.local_titular_ready`) — así el banco y el motor no pueden discrepar
    # sobre qué significa «está el modelo».
    from nucleo import memllm as _memllm
    _kept: list[str] = []
    for n in names:
        _u, _m = CANDIDATES[n]
        if _memllm.is_local_endpoint(_u) and not _memllm.local_titular_ready(_u, _m):
            print(f"⏭️  {n}: {_m} no está en este Ollama (o no responde) → SALTADO, no puntúa 0", file=sys.stderr)
            continue
        _kept.append(n)
    names = _kept

    if args.preflight:
        print(f"PREFLIGHT — {len(names)} candidatos")
        await _preflight(names)
        return

    results = []
    for name in names:
        url, model = CANDIDATES[name]
        print(f"→ {name} ({model} @ {url.split('//')[1].split('/')[0]}) …", flush=True)
        runs = []
        for i in range(max(1, args.runs)):
            try:
                runs.append(await run_model(name, url, model))
            except Exception as e:  # noqa: BLE001
                runs.append({"model": name, "error": str(e)[:200]})
        ok_runs = [r for r in runs if "completeness_pct" in r]
        if not ok_runs:
            r = {"model": name, "error": runs[0].get("error", "sin resultado")}
        elif len(ok_runs) == 1:
            r = ok_runs[0]
        else:
            r = dict(ok_runs[0])
            for k in ("completeness_pct", "precision_pct", "layer_pct", "avg_in_tok", "avg_out_tok"):
                r[k] = round(statistics.mean(x[k] for x in ok_runs), 1)
            r["p50_ms"] = int(statistics.median([x["p50_ms"] for x in ok_runs]))
            r["dead_calls"] = sum(x["dead_calls"] for x in ok_runs)
            r["runs"] = len(ok_runs)
            r["spread"] = {k: [x[k] for x in ok_runs] for k in ("completeness_pct", "precision_pct", "layer_pct")}
            r["misses"] = sorted({m for x in ok_runs for m in x["misses"]})
        r["usd_per_1k_turns"] = _cost_per_1k(r) if "completeness_pct" in r else None
        results.append(r)
        if "completeness_pct" in r:
            print(f"   compl={r['completeness_pct']}%  prec={r['precision_pct']}%  capa/slot={r['layer_pct']}%  "
                  f"${r['usd_per_1k_turns']}/1k  p50={r['p50_ms']}ms  muertas={r['dead_calls']}", flush=True)
        else:
            print(f"   ERROR: {r['error'][:140]}", flush=True)

    tag = f"-{args.tag}" if args.tag else ""
    out = Path(__file__).parent / "resultados" / f"{time.strftime('%Y%m%d')}-distiller-bench{tag}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    ok = [r for r in results if "completeness_pct" in r]
    lines = [f"# Bench del DESTILADOR (CORAZÓN) — calidad vs precio — {time.strftime('%Y-%m-%d %H:%M')}", "",
             f"{len(CASES)} casos · {args.runs} pasada(s) · la latencia NO puntúa (escritor off-hot-path)", "",
             "| modelo | write-compl. | precisión | capa/slot | $/1k turnos | in/out tok | p50 | muertas |",
             "|---|---|---|---|---|---|---|---|"]
    for r in sorted(ok, key=lambda x: (-x["completeness_pct"], -x["precision_pct"])):
        cost = f"${r['usd_per_1k_turns']}" if r.get("usd_per_1k_turns") is not None else "—"
        lines.append(f"| {r['model']} | {r['completeness_pct']}% | {r['precision_pct']}% | {r['layer_pct']}% | "
                     f"{cost} | {r['avg_in_tok']}/{r['avg_out_tok']} | {r['p50_ms']}ms | {r['dead_calls']} |")
    for r in results:
        if "error" in r:
            lines.append(f"| {r['model']} | ERROR | — | — | — | — | — | {r['error'][:80]} |")
    (out / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nresultados → {out}")


if __name__ == "__main__":
    asyncio.run(main())
