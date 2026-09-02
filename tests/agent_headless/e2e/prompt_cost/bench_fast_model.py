"""Which fast model can handle the VOICE turn? A/B benchmark against the REAL production prompt.

It stems from an operator observation (2026-08-02): «We had measured DeepSeek V4 Flash as equally fast or faster than
another model; in production, latency is horrible. We should run the benchmarks again, but on the real agent and
launching requests in parallel». The old benchmarks measured toy prompts; production sends 13k tokens and
23 tools. This benchmark measures the SAME thing the operator experiences:

  · the REAL prompt, extracted from the timeline (`system_prompt` from the `perf` events already recorded),
  · the REAL tool catalog (`router.TOOLS`),
  · TTFT and total time, which is what is noticeable in voice (TTS does not start until the first token),
  · ROUTING (if a model is fast but chooses the wrong tool, it is no use),
  · and a PARALLEL burst, because a proxy that performs well one at a time may queue under load.

Usage (requires the server to be running for credentials; does not touch memory or state):
    ./.venv/bin/python -m tests.agent_headless.e2e.prompt_cost.bench_fast_model \
        [--only lat|par|route] [--reps N] [--models subcadena,subcadena]

`--models` exists because the full benchmark has 20 candidates: at 3 rounds × 14 cases that is 840 calls, and providers
start returning 429 halfway through — the numbers become contaminated and no decision can be made from them.
To answer ONE question (does this model replace the primary?) compare TWO arms and stop there.
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

# Candidates. The first is the one in production TODAY; the rest are those that responded to the availability ping.
# `aimlapi` is a BROKER (proxy with markup); the others are the DIRECT provider — comparing the same
# model type through each route is precisely what separates a «slow model» from a «slow intermediary».
CANDIDATES: list[tuple[str, ModelSpec]] = [
    ("aiml·deepseek-v4-flash", ModelSpec("deepseek/deepseek-v4-flash", AIML, provider="aimlapi")),
    # SAME model, OWN endpoint (2026-08-14). It is not a duplicate: the broker ACCEPTS
    # `thinking:{"type":"disabled"}` and reasons anyway, while `api.deepseek.com` OBEYS it — measured, TTFT p50 4.24→1.01 s,
    # worst case 14.71→1.30 s, and 2,138→0 reasoning tokens (`usage.completion_tokens_details.reasoning_tokens`,
    # which was the missing evidence needed on 2026-08-02 to close that diagnosis).
    # It is here because it is a PRIMARY CANDIDATE and this benchmark makes the decision: in a single run it scored 12/14 against
    # the broker's 14/14, and with one sample per case that is not enough to promote or reject it. Today it is
    # the first latency-based replacement step (V2-094); if it holds 14/14 for 3 rounds, it becomes primary (V2-097 §1).
    ("deepseek·directo", ModelSpec("deepseek-v4-flash", "https://api.deepseek.com", provider="aimlapi")),
    ("deepseek·directo-pro", ModelSpec("deepseek-v4-pro", "https://api.deepseek.com", provider="aimlapi")),
    # V4 Flash REASONS even when asked not to (measured 2026-08-02: the `thinking:disabled` flag only reduces it,
    # from 2489 to 993 reasoning chars) — and VOICE is non-reasoning by invariant. These two variants
    # declare it in the model name itself, which is the only reliable way to disable it through the broker.
    ("aiml·deepseek-non-thinking", ModelSpec("deepseek/deepseek-non-thinking-v3.2-exp", AIML, provider="aimlapi")),
    ("aiml·deepseek-non-reasoner", ModelSpec("deepseek/deepseek-non-reasoner-v3.1-terminus", AIML,
                                             provider="aimlapi")),
    ("aiml·gemini-3.7-flash", ModelSpec("google/gemini-3.7-flash", AIML, provider="aimlapi")),
    ("aiml·gemini-3.6-flash", ModelSpec("google/gemini-3.6-flash", AIML, provider="aimlapi")),
    ("aiml·gemini-3.5-flash", ModelSpec("google/gemini-3.5-flash", AIML, provider="aimlapi")),
    ("aiml·gemini-3.5-flash-lite", ModelSpec("google/gemini-3.5-flash-lite", AIML, provider="aimlapi")),
    ("aiml·gemini-2.5-flash", ModelSpec("google/gemini-2.5-flash", AIML, provider="aimlapi")),
    ("openai·gpt-4.1-mini", ModelSpec("gpt-4.1-mini", OPENAI, provider="openai")),
    ("mistral·medium-latest", ModelSpec("mistral-medium-latest", MISTRAL, provider="mistral")),
    # xAI DIRECT (without a broker). Grok has been BANNED in FlashBrain since it misrouted memory→widget_data,
    # but that was another generation: these declare «non-reasoning» in the name, which is exactly the voice invariant
    # and exactly what DeepSeek V4 Flash does not satisfy. The ban is lifted with data, or it is not lifted.
    ("xai·grok-4.20-non-reasoning", ModelSpec("grok-4.20-0309-non-reasoning", XAI, provider="xai")),
    ("xai·grok-4.5", ModelSpec("grok-4.5", XAI, provider="xai")),
    ("xai·grok-4.3", ModelSpec("grok-4.3", XAI, provider="xai")),
    ("aiml·grok-4-1-fast-non-reas", ModelSpec("x-ai/grok-4-1-fast-non-reasoning", AIML, provider="aimlapi")),
    # Gemini DIRECT: the fastest in the benchmark, but the operator's key is on the free tier (20 req/day) → 429.
    # It remains declared so it can be measured again when billing is enabled.
    ("gemini·2.5-flash (free)", ModelSpec("gemini-2.5-flash", GEMINI, provider="gemini")),
]

# ROUTING cases: the mix actually seen in a voice turn (chat, fact, widget, task, media, panel).
# Each case is (name, turn, accepted, FORBIDDEN). Empty `accepted` = it must not call any tool;
# `forbidden` marks the specific SERIOUS failure, the one that breaks a conversation rather than merely falling short.
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
    # V2-556: hunting ADS is the listing fast pass now (the module itself escalates when the market answers
    # thin) — while DOING something on a marketplace (buying, booking) is still a worker. Both directions pinned.
    ("marketplace", "busca motos naked de segunda mano en Wallapop", {"search_listings"}, set()),
    # operar: with no antecedent in a bare prompt, asking which one (no tool) is legitimate — what BREAKS is
    # treating a purchase as a hunt, so search_listings is the FORBIDDEN answer here, not the missed escalate.
    ("marketplace-operar", "entra en Wallapop y cómprame esa moto, gestiona tú la compra",
     {"escalate_to_slowbrain"}, {"search_listings"}),
    ("alias", "llama a este widget «mi informe»", {"manage_widget_alias"}, set()),
    # ── QUESTION ≠ COMMAND ──────────────────────────────────────────────────────────────────────────────────
    # The EXACT turn that got grok banned from FlashBrain (A/B 2026-07-17, `zaelar-model-benchmarks.md §9`):
    # with the answer in front of it in the prompt, it replied «Done» and called `widget_data`. Routing a
    # QUESTION to an ACTION is what the operator called «absurd conversations», and none of the
    # cases above catches it. Responding without a tool or looking at memory is acceptable; TOUCHING data is not.
    ("pregunta memoria", "dime cuándo es la cita de la ITV", {"recall", "show_widget"},
     {"widget_data", "escalate_to_slowbrain", "delete_widget"}),
    ("pregunta estado", "¿cuántas tareas tienes en marcha?", set(),
     {"widget_data", "escalate_to_slowbrain", "delete_widget"}),
]

_TIMELINE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))), ".meshkore", "logs", "timeline-latest.jsonl")


def real_system_prompt() -> str:
    """The REAL system prompt for the voice turn. It is BUILT with the same constructor production uses
    (`prompt.build_flash_system`) — reading it from the timeline is not valid: it is stored there TRUNCATED to 8000 chars, and measuring with
    half a prompt is exactly the error this benchmark is intended to correct. The timeline remains a fallback if building
    fails (no session, no memory)."""
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
    """One measured turn: TTFT (first TEXT token — what unlocks TTS), total time, tokens, and selected tools."""
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
    """The candidates to measure. Without `--models`, all of them (the panoramic view). With `--models`, those that
    contain any of the substrings — which is how a decision is MADE; see the docstring."""
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
    """(correct, serious). A case with `forbidden` is a QUESTION: the bar is not converting it into an ACTION,
    so replying without a tool counts as correct. Calling a forbidden tool is SERIOUS — it is not merely falling short;
    it is doing something nobody asked for, and that is what breaks a conversation."""
    grave = bool(got & forbidden)
    if forbidden:
        return (not grave), grave
    return ((not expect and not got) or bool(got & expect)), grave


async def exp_routing(system: str, reps: int = 1, models: str | None = None) -> None:
    """Routing over N rounds. Until 2026-08-15 this experiment IGNORED `--reps` and ran each case ONCE;
    the docs mentioned «3 rounds» but the code did not do them. With one sample per case, 12/14 and 14/14 are not
    distinguishable from the model's own variance, so the primary decision depending on this number could not be made.
    Now each case is repeated and failures are reported with their FREQUENCY (`case→tools (2/3)`):
    failing 3 of 3 is a routing defect, failing 1 of 3 is noise, and the difference decides."""
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
