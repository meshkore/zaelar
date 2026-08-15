"""¿Qué modelo rápido aguanta el turno de VOZ? Banco A/B contra el prompt REAL de producción.

Nace de una observación del operador (2026-08-02): «DeepSeek V4 Flash lo habíamos medido igual o más rápido que
Haiku; en producción la latencia es horrible. Deberíamos volver a pasar los benchmarks, pero en el agente real y
lanzando peticiones en paralelo». Los benchmarks viejos medían prompts de juguete; producción manda 13k tokens y
23 tools. Este banco mide lo MISMO que sufre el operador:

  · el prompt REAL, extraído del timeline (`system_prompt` de los eventos `perf` que ya se registran),
  · el catálogo REAL de tools (`router.TOOLS`),
  · TTFT y total, que es lo que se nota en la voz (el TTS no empieza hasta el primer token),
  · el ENRUTADO (si un modelo es rápido pero elige mal la tool, no sirve),
  · y una ráfaga en PARALELO, porque un proxy que va bien de uno en uno puede encolar bajo carga.

Uso (exige el server vivo para las credenciales; no toca memoria ni estado):
    ./.venv/bin/python -m tests.agent_headless.e2e.prompt_cost.bench_fast_model \
        [--only lat|par|route] [--reps N] [--models subcadena,subcadena]

`--models` existe porque el banco entero son 20 candidatos: a 3 rondas × 14 casos eso son 840 llamadas y los
proveedores empiezan a devolver 429 a media tabla — los números salen contaminados y no se puede decidir nada con
ellos. Para resolver UNA pregunta (¿este modelo sustituye al titular?) se comparan DOS brazos y ya.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time

import server.common  # noqa: F401  — carga el credential store en el entorno

from nucleo.flash import router
from nucleo.flash.fast_client import FastClient, ModelSpec

AIML = "https://api.aimlapi.com/v1"
GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai/"
OPENAI = "https://api.openai.com/v1"
MISTRAL = "https://api.mistral.ai/v1"
XAI = "https://api.x.ai/v1"

# Candidatos. El primero es el de producción HOY; el resto son los que respondieron al ping de disponibilidad.
# `aimlapi` es un BROKER (proxy con margen); los demás son el proveedor DIRECTO — la comparación entre el mismo
# tipo de modelo por una vía y por la otra es justamente lo que separa «modelo lento» de «intermediario lento».
CANDIDATES: list[tuple[str, ModelSpec]] = [
    ("aiml·deepseek-v4-flash", ModelSpec("deepseek/deepseek-v4-flash", AIML, provider="aimlapi")),
    # MISMO modelo, endpoint PROPIO (2026-08-14). No es un duplicado: el broker ACEPTA
    # `thinking:{"type":"disabled"}` y razona igual, `api.deepseek.com` lo OBEDECE — medido, TTFT p50 4,24→1,01 s,
    # peor caso 14,71→1,30 s, y 2.138→0 tokens de razonamiento (`usage.completion_tokens_details.reasoning_tokens`,
    # que es la prueba que faltaba el 2026-08-02 para cerrar aquel diagnóstico).
    # Está aquí porque es CANDIDATO A TITULAR y la decisión es de este banco: en una pasada suelta dio 12/14 contra
    # el 14/14 del broker, y con una sola muestra por caso eso no basta para promoverlo ni para descartarlo. Hoy es
    # el primer escalón de relevo por latencia (V2-094); si aguanta 14/14 a 3 rondas, pasa a titular (V2-097 §1).
    ("deepseek·directo", ModelSpec("deepseek-v4-flash", "https://api.deepseek.com", provider="aimlapi")),
    ("deepseek·directo-pro", ModelSpec("deepseek-v4-pro", "https://api.deepseek.com", provider="aimlapi")),
    # V4 Flash RAZONA aunque se le pida que no (medido 2026-08-02: el flag `thinking:disabled` solo lo reduce,
    # de 2489 a 993 chars de razonamiento) — y la VOZ es no-razonadora por invariante. Estas dos variantes lo
    # declaran en el propio nombre del modelo, que es la única forma fiable de apagarlo a través del broker.
    ("aiml·deepseek-non-thinking", ModelSpec("deepseek/deepseek-non-thinking-v3.2-exp", AIML, provider="aimlapi")),
    ("aiml·deepseek-non-reasoner", ModelSpec("deepseek/deepseek-non-reasoner-v3.1-terminus", AIML,
                                             provider="aimlapi")),
    ("aiml·haiku-4.5", ModelSpec("anthropic/claude-haiku-4.5", AIML, provider="aimlapi")),
    ("aiml·gemini-3.7-flash", ModelSpec("google/gemini-3.7-flash", AIML, provider="aimlapi")),
    ("aiml·gemini-3.6-flash", ModelSpec("google/gemini-3.6-flash", AIML, provider="aimlapi")),
    ("aiml·gemini-3.5-flash", ModelSpec("google/gemini-3.5-flash", AIML, provider="aimlapi")),
    ("aiml·gemini-3.5-flash-lite", ModelSpec("google/gemini-3.5-flash-lite", AIML, provider="aimlapi")),
    ("aiml·gemini-2.5-flash", ModelSpec("google/gemini-2.5-flash", AIML, provider="aimlapi")),
    ("openai·gpt-4.1-mini", ModelSpec("gpt-4.1-mini", OPENAI, provider="openai")),
    ("mistral·medium-latest", ModelSpec("mistral-medium-latest", MISTRAL, provider="mistral")),
    # xAI DIRECTO (sin broker). Grok está BANEADO en el FlashBrain desde que mis-ruteaba memoria→widget_data,
    # pero aquella era otra generación: estos declaran «non-reasoning» en el nombre, que es justo el invariante
    # de la voz y justo lo que DeepSeek V4 Flash no cumple. El ban se levanta con datos o no se levanta.
    ("xai·grok-4.20-non-reasoning", ModelSpec("grok-4.20-0309-non-reasoning", XAI, provider="xai")),
    ("xai·grok-4.5", ModelSpec("grok-4.5", XAI, provider="xai")),
    ("xai·grok-4.3", ModelSpec("grok-4.3", XAI, provider="xai")),
    ("aiml·grok-4-1-fast-non-reas", ModelSpec("x-ai/grok-4-1-fast-non-reasoning", AIML, provider="aimlapi")),
    # Gemini DIRECTO: el más rápido del banco, pero la key del operador está en free tier (20 req/día) → 429.
    # Se deja declarado para volver a medirlo el día que se active facturación.
    ("gemini·2.5-flash (free)", ModelSpec("gemini-2.5-flash", GEMINI, provider="gemini")),
]

# Casos de ENRUTADO: la mezcla que de verdad se ve en un turno de voz (charla, dato, widget, tarea, media, panel).
# Cada caso es (nombre, turno, aceptadas, PROHIBIDAS). `aceptadas` vacío = no debe llamar a ninguna tool;
# `prohibidas` marca el fallo GRAVE concreto, el que rompe una conversación en vez de solo quedarse corto.
CASES: list[tuple[str, str, set[str], set[str]]] = [
    ("charla", "hola, ¿qué tal todo?", set(), set()),
    ("dato del mundo", "¿cuánto cuesta la entrada de Aquopolis?", {"web_search"}, set()),
    ("mostrar widget", "muéstrame el widget de resultados", {"show_widget"}, set()),
    ("data-op", "elige el primero de la lista de resultados", {"widget_data"}, set()),
    ("tarea larga", "investiga en internet y ponme un informe de 3 parques acuáticos en pantalla",
     {"escalate_to_slowbrain"}, set()),
    ("música", "pon música de jazz", {"play_music"}, set()),
    ("vídeo", "pon el vídeo del último gol del Barça", {"play_video"}, set()),
    ("panel", "abre el chat", {"show_panel"}, set()),
    ("estilo", "a partir de ahora sé más breve", {"set_style_directive"}, set()),
    ("borrar widget", "borra el widget de resultados", {"delete_widget"}, set()),
    ("marketplace", "busca motos naked de segunda mano en Wallapop", {"escalate_to_slowbrain"}, set()),
    ("alias", "llama a este widget «mi informe»", {"manage_widget_alias"}, set()),
    # ── PREGUNTA ≠ ORDEN ──────────────────────────────────────────────────────────────────────────────────
    # El turno EXACTO que baneó a grok del FlashBrain (A/B 2026-07-17, `zaelar-model-benchmarks.md §9`):
    # teniendo la respuesta delante en el prompt, contestó «Hecho» y llamó a `widget_data`. Enrutar una
    # PREGUNTA a una ACCIÓN es lo que el operador llamó «conversaciones absurdas», y no lo caza ninguno de los
    # casos de arriba. Responder sin tool o mirar la memoria valen; TOCAR datos no.
    ("pregunta memoria", "dime cuándo es la cita de la ITV", {"recall", "show_widget"},
     {"widget_data", "escalate_to_slowbrain", "delete_widget"}),
    ("pregunta estado", "¿cuántas tareas tienes en marcha?", set(),
     {"widget_data", "escalate_to_slowbrain", "delete_widget"}),
]

_TIMELINE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))), ".meshkore", "logs", "timeline-latest.jsonl")


def real_system_prompt() -> str:
    """El system prompt REAL del turno de voz. Se COMPONE con el mismo constructor que usa producción
    (`prompt.build_flash_system`) — leerlo del timeline no vale: ahí se guarda RECORTADO a 8000 chars, y medir con
    medio prompt es justo el error que este banco viene a corregir. El timeline queda de reserva por si componer
    falla (sin sesión, sin memoria)."""
    try:
        from nucleo.flash import prompt as _p
        built, _ids = _p.build_flash_system(turn_text="investiga en internet y ponme un informe en pantalla")
        if built:
            return built
    except Exception as e:  # noqa: BLE001
        print(f"(no se pudo componer el prompt real: {type(e).__name__}: {e}; caigo al timeline)")
    best = ""
    try:
        with open(_TIMELINE, encoding="utf-8") as fh:
            for line in fh:
                if '"system_prompt"' not in line:
                    continue
                try:
                    sp = (json.loads(line).get("system_prompt") or "")
                except Exception:
                    continue
                if len(sp) > len(best):
                    best = sp
    except FileNotFoundError:
        pass
    return best


async def one_call(client: FastClient, spec: ModelSpec, system: str, user: str,
                   tools: list[dict] | None) -> dict:
    """Un turno medido: TTFT (primer token de TEXTO — lo que desbloquea el TTS), total, tokens y tools elegidas."""
    got: list[str] = []
    m: dict = {}
    t0 = time.time()
    ttft = None
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        async for chunk in client.stream(msgs, spec=spec, tools=tools, max_tokens=260,
                                         on_tool_call=lambda n, a: got.append(n), metrics=m):
            if ttft is None and chunk:
                ttft = (time.time() - t0) * 1000
    except Exception as e:  # noqa: BLE001 — un candidato caído no debe tirar el banco entero
        return {"error": f"{type(e).__name__}: {str(e)[:70]}", "total_ms": (time.time() - t0) * 1000}
    total = (time.time() - t0) * 1000
    ctok = m.get("completion_tokens") or m.get("completion_tokens_est") or 0
    return {"total_ms": total, "ttft_ms": ttft, "tools": set(got),
            "ptok": m.get("prompt_tokens") or m.get("prompt_tokens_est") or 0, "ctok": ctok,
            "tok_s": (ctok / (total / 1000)) if total and ctok else 0.0}


def _selected(only: str | None) -> list[tuple[str, ModelSpec]]:
    """Los candidatos que se van a medir. Sin `--models`, todos (la foto panorámica). Con `--models`, los que
    contengan alguna de las subcadenas — que es el modo en que se DECIDE algo, ver el docstring."""
    if not only:
        return CANDIDATES
    pats = [p.strip().lower() for p in only.split(",") if p.strip()]
    return [(lab, sp) for lab, sp in CANDIDATES if any(p in lab.lower() for p in pats)]


def _usable(spec: ModelSpec) -> bool:
    try:
        return bool(spec.resolved_api_key())
    except Exception:
        return False


async def exp_latency(system: str, reps: int, models: str | None = None) -> None:
    print("── A · LATENCIA CON EL PROMPT REAL (secuencial, conexión caliente) ──")
    print(f"prompt real {len(system)} chars (~{len(system)//4} tok) + {len(router.TOOLS)} tools "
          f"({sum(len(json.dumps(t, ensure_ascii=False)) for t in router.TOOLS)} chars)\n")
    print(f"{'candidato':24} {'total p50':>10} {'ttft p50':>10} {'peor':>8} {'tok/s':>7}   entrada")
    for label, spec in _selected(models):
        if not _usable(spec):
            print(f"{label:24} — sin credencial")
            continue
        c = FastClient()
        runs = []
        for _ in range(reps):
            r = await one_call(c, spec, system, "investiga en internet y ponme un informe de 3 parques en pantalla",
                               router.TOOLS)
            runs.append(r)
            await asyncio.sleep(0.5)
        bad = [r for r in runs if r.get("error")]
        ok = [r for r in runs if not r.get("error")]
        if not ok:
            print(f"{label:24} FALLA {bad[0]['error']}")
            continue
        tot = statistics.median(r["total_ms"] for r in ok)
        tt = [r["ttft_ms"] for r in ok if r["ttft_ms"] is not None]
        ttft = statistics.median(tt) if tt else None
        print(f"{label:24} {tot:8.0f} ms {(f'{ttft:.0f} ms' if ttft else '(sin texto)'):>10} "
              f"{max(r['total_ms'] for r in ok):6.0f} ms {statistics.median(r['tok_s'] for r in ok):7.1f}   "
              f"{ok[0]['ptok']} tok" + (f"  [{len(bad)} fallo(s)]" if bad else ""))
    print()


async def exp_parallel(system: str, n: int = 4, models: str | None = None) -> None:
    print(f"── B · RÁFAGA EN PARALELO ({n} peticiones a la vez) ──")
    print("un proveedor que va bien de uno en uno puede encolar bajo carga; la voz real solapa turnos.\n")
    print(f"{'candidato':24} {'1 sola':>9} {'p50 de ' + str(n):>12} {'peor de ' + str(n):>12}   degradación")
    for label, spec in _selected(models):
        if not _usable(spec):
            continue
        c = FastClient()
        solo = await one_call(c, spec, system, "¿cuánto cuesta la entrada de Aquopolis?", router.TOOLS)
        if solo.get("error"):
            print(f"{label:24} FALLA {solo['error']}")
            continue
        await asyncio.sleep(0.5)
        burst = await asyncio.gather(*[
            one_call(c, spec, system, f"¿cuánto cuesta la entrada de Aquopolis? ({i})", router.TOOLS)
            for i in range(n)])
        ok = [r for r in burst if not r.get("error")]
        if not ok:
            print(f"{label:24} paralelo FALLA {burst[0].get('error')}")
            continue
        p50 = statistics.median(r["total_ms"] for r in ok)
        worst = max(r["total_ms"] for r in ok)
        print(f"{label:24} {solo['total_ms']:7.0f} ms {p50:10.0f} ms {worst:10.0f} ms   "
              f"×{p50 / solo['total_ms']:.1f}" + (f"  [{n - len(ok)} fallo(s)]" if len(ok) < n else ""))
        await asyncio.sleep(0.5)
    print()


def score(got: set[str], expect: set[str], forbidden: set[str]) -> tuple[bool, bool]:
    """(acierta, es_grave). Un caso con `forbidden` es una PREGUNTA: el listón es no convertirla en una ACCIÓN,
    así que responder sin tool cuenta como acierto. Llamar a una tool prohibida es GRAVE — no es quedarse corto,
    es hacer algo que nadie pidió, y eso es lo que rompe una conversación."""
    grave = bool(got & forbidden)
    if forbidden:
        return (not grave), grave
    return ((not expect and not got) or bool(got & expect)), grave


async def exp_routing(system: str, reps: int = 1, models: str | None = None) -> None:
    """El enrutado a N rondas. Hasta el 2026-08-15 este experimento IGNORABA `--reps` y corría cada caso UNA vez;
    la doc hablaba de «3 rondas» y el código no las hacía. Con una sola muestra por caso, un 12/14 y un 14/14 no
    son distinguibles de la varianza del propio modelo, así que la decisión de titular que colgaba de este número
    no se podía tomar. Ahora cada caso se repite y el fallo se reporta con su FRECUENCIA (`caso→tools (2/3)`):
    fallar 3 de 3 es un defecto de enrutado, fallar 1 de 3 es ruido, y la diferencia decide."""
    print(f"── C · ENRUTADO: rápido no vale si elige mal la tool ({reps} ronda(s)) ──\n")
    print(f"{'candidato':28} {'acierto':>9} {'graves':>7} {'p50':>9}   fallos")
    for label, spec in _selected(models):
        if not _usable(spec):
            continue
        c = FastClient()
        hits, graves, lat, fails = 0, 0, [], {}
        for _ in range(reps):
            for name, text, expect, forbidden in CASES:
                r = await one_call(c, spec, system, text, router.TOOLS)
                if r.get("error"):
                    fails[f"{name}!"] = fails.get(f"{name}!", 0) + 1
                    continue
                lat.append(r["total_ms"])
                ok, grave = score(r["tools"], expect, forbidden)
                hits += int(ok)
                graves += int(grave)
                if not ok:
                    k = f"{'⛔' if grave else ''}{name}→{sorted(r['tools']) or '—'}"
                    fails[k] = fails.get(k, 0) + 1
                await asyncio.sleep(0.4)
        miss = [f"{k} ({n}/{reps})" for k, n in sorted(fails.items(), key=lambda kv: -kv[1])]
        print(f"{label:28} {hits:>4}/{len(CASES) * reps} {graves:>7} "
              f"{(statistics.median(lat) if lat else 0):7.0f} ms   {', '.join(miss) or '—'}")
    print()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["lat", "par", "route"])
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--models", help="subcadenas separadas por coma; sin esto se miden los 20 candidatos")
    a = ap.parse_args()
    system = real_system_prompt()
    if not system:
        print("no hay prompt real en el timeline — habla una vez con el agente y repite")
        return
    if a.only in (None, "lat"):
        await exp_latency(system, a.reps, a.models)
    if a.only in (None, "par"):
        await exp_parallel(system, models=a.models)
    if a.only in (None, "route"):
        await exp_routing(system, a.reps, a.models)


if __name__ == "__main__":
    asyncio.run(main())
