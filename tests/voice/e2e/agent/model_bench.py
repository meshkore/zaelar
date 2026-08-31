"""tests/voice/e2e/agent/model_bench.py — FlashBrain's own model-selection BENCHMARK (latency ↔ intelligence).

The PROBLEM: perceived voice latency is dominated by the **TTFT of the fast model** (the AIMLAPI routing
provider is not the bottleneck — verified; it is the model itself that takes time to emit the first token). This script
measures, through FlashBrain's REAL PATH (same `build_flash_system` system prompt + same `router.TOOLS` +
OpenAI-compatible streaming with `tool_choice=auto`), three things for each candidate model:

  · **TTFT** (time-to-first-token/tool-delta) — what makes the voice feel lively or slow. The king metric.
  · **total** — until the short response is complete.
  · **ROUTING accuracy** — does it choose the right tool for each turn? (objective proxy for "intelligence" for
    FlashBrain: grok's failure was "it did not search when it should have").

It changes NOTHING in production: it does not touch `config/v2` or reconfigure the server. It only makes measurement calls.
It is a REUSABLE test — run it whenever you want to re-evaluate the model shortlist.

Uso:
    ./.venv/bin/python -m tests.voice.e2e.agent.model_bench                 # shortlist por defecto, 3 reps
    ./.venv/bin/python -m tests.voice.e2e.agent.model_bench --reps 4        # más reps (promedia varianza de Cloudflare)
    ./.venv/bin/python -m tests.voice.e2e.agent.model_bench --models "deepseek-v4-pro,google/gemini-3.7-flash"
    ./.venv/bin/python -m tests.voice.e2e.agent.model_bench --gemini-direct # añade Gemini por el endpoint google-directo (thinking OFF)

Keys: AIMLAPI_KEY (cloud) and GEMINI_API_KEY (google-direct) from the environment (.env), just like fast_client.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from dataclasses import dataclass

# ── load .env as the server does (best-effort) ────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from nucleo.flash.router import TOOLS  # noqa: E402

_BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


# ── candidatos ──────────────────────────────────────────────────────────────────────────────────────────────
@dataclass
class Candidate:
    label: str
    model: str
    base_url: str
    api_key_env: str
    reasoning_off: bool = False   # sends reasoning_effort='none' (only the google-direct endpoint accepts it)
    extra_body: dict | None = None   # arbitrary extra_body (e.g. DeepSeek non-thinking: {"thinking":{"type":"disabled"}})


def _aimlapi(model: str) -> Candidate:
    return Candidate(f"aimlapi/{model}", model, "https://api.aimlapi.com/v1", "AIMLAPI_KEY")


def _gemini_direct(model: str) -> Candidate:
    # Google's OpenAI-compatible endpoint; the model goes WITHOUT the 'google/' prefix
    m = model.split("/")[-1]
    return Candidate(f"google-direct/{m}", m,
                     "https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY",
                     reasoning_off=True)


DEFAULT_MODELS = [
    "x-ai/grok-4-fast-non-reasoning",       # tested: fast but "not very smart"
    "google/gemini-2.5-flash",              # smartest of the fast trio; may activate thinking
    "google/gemini-3-5-flash",              # ★ operator's candidate
    "google/gemini-3-flash-preview",        # gemini 3 flash
    "deepseek/deepseek-v4-flash",           # el más barato/lento del shortlist
]


# ── test turns: (id, text, expected route) ────────────────────────────────────────────────────────────
# expected route: 'chat' (no tool or tag), 'web_search', 'canvas' (tag [[show..]]), 'escalate'
# each turn: (id, text, expected_route, category). cat="routing" → measures dispatch (does it call the right tool?);
# cat="intel" → measures INTELLIGENCE (introspection, not hallucinating, not over-acting, resolving contradictions). The
# routing ones are almost all passed; the intel ones DISCRIMINATE the speed of TRUE intelligence (grok's gap).
TURNS = [
    # ── ROUTING (dispatch) — each turn has a UNIQUE, unambiguous route (if ambiguous, it adds noise, not signal) ──
    ("chat",       "Oye, ¿qué tal va todo? Cuéntame algo.",                                  "chat",        "routing"),
    ("search",     "¿Qué tiempo va a hacer mañana en Soria?",                                "web_search",  "routing"),
    ("search2",    "¿A qué hora abre hoy el Mercadona de mi barrio?",                         "web_search",  "routing"),
    ("widget",     "Muéstrame un reloj en la pantalla.",                                     "canvas",      "routing"),
    ("widget2",    "Ábreme la agenda.",                                                      "canvas",      "routing"),
    ("widget_data","Añade una cita mañana a las cinco de la tarde en la agenda.",            "widget_data", "routing"),
    ("music",      "Pon algo de música de los Beatles.",                                     "play_music",  "routing"),
    ("delete",     "Borra el widget del reloj.",                                             "delete_widget","routing"),
    ("recall",     "¿Te acuerdas de cómo me llamo?",                                         "chat",        "routing"),
    ("escalate",   "Búscame en Wallapop una moto de enduro de segunda mano por menos de 4000 euros cerca de mí.", "escalate", "routing"),
    # ── INTELLIGENCE (HARD turns that discriminate; almost all should stay in `chat`, with no spurious action) ──
    # META: asking about its own behavior is NOT an instruction to act → it must EXPLAIN, not open/search anything.
    ("meta",        "¿Por qué has hecho eso? No te había pedido que abrieras nada.",         "chat", "intel"),
    # CONTRADICTION: it must acknowledge/resolve it, not double down or hallucinate a tool.
    ("contra",      "Antes has dicho que sí y ahora dices que no. ¿En qué quedamos?",        "chat", "intel"),
    # DO NOT SEARCH (trap): a trivial calculation is solved ALONE, not with web_search.
    ("nosearch",    "¿Cuánto es el quince por ciento de doscientos euros?",                  "chat", "intel"),
    # DO NOT ACT: explicit instruction to do NOTHING yet → zero tools/tags, just acknowledge receipt.
    ("noact",       "No abras ni cambies nada todavía, solo escúchame un momento, ¿vale?",   "chat", "intel"),
    # INTROSPECTION: META question about capabilities → explain naturally, without triggering an action.
    ("introspect",  "¿Tú cómo sabes lo que tengo abierto en la pantalla ahora mismo?",       "chat", "intel"),
    # COMMENT (not an instruction): observation about something on screen → do NOT touch the canvas; continue the conversation.
    ("comment",     "Qué pequeño se ve ese reloj, ¿no?",                                     "chat", "intel"),
]


def _build_prompt(text: str) -> tuple[str, list[dict]]:
    """FlashBrain's REAL prompt for this turn (same build as voice/probe). Fallback: minimal prompt."""
    try:
        from nucleo.flash.prompt import build_flash_system, compose_recent_block, needs_recall, needs_recent
        recall_q = text if needs_recall(text) else ""
        recent_block = compose_recent_block() if needs_recent(text) else ""
        system, _ = build_flash_system(directive="", recall_query=recall_q, recent_block=recent_block)
        return system, [{"role": "system", "content": system}, {"role": "user", "content": text}]
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ build_flash_system falló ({e}); uso prompt mínimo")
        system = "Eres zaelar, un asistente de voz en español. Responde breve y natural."
        return system, [{"role": "system", "content": system}, {"role": "user", "content": text}]


def _route_of(content: str, tool_names: list[str]) -> str:
    if "escalate_to_slowbrain" in tool_names:
        return "escalate"
    if "web_search" in tool_names:
        return "web_search"
    if "widget_data" in tool_names:
        return "widget_data"
    # SHOW/OPEN a widget = "canvas" route, both through the first-class TOOL `show_widget`/`fullscreen_widget`
    # (which converges on [[show:id]], router.TOOLS) and through the inline TAG [[show]]. Both are correct → count them
    # equally (noise-reduced 2026-07-31: previously only the tag counted, falsely penalizing tool use).
    if any(t in tool_names for t in ("show_widget", "fullscreen_widget")):
        return "canvas"
    if any(t in content for t in ("[[show", "[[close", "[[move")):
        return "canvas"
    if tool_names:
        return tool_names[0]
    return "chat"


async def _one_call(cli, model: str, messages: list[dict], reasoning_off: bool,
                    extra_body: dict | None = None) -> dict:
    """One streaming call; measures TTFT (1st chunk of ANY kind) and total. Replicates fast_client."""
    kwargs = dict(model=model, messages=messages, max_tokens=200, stream=True,
                  tools=TOOLS, tool_choice="auto")
    extra: dict = dict(extra_body or {})
    if reasoning_off:
        extra["reasoning_effort"] = "none"
    if extra:
        kwargs["extra_body"] = extra
    t0 = time.time()
    ttft = None
    content = ""
    calls: dict[int, dict] = {}
    try:
        stream = await cli.chat.completions.create(**kwargs)
        async for chunk in stream:
            if ttft is None:
                ttft = time.time() - t0          # first event in the stream, whether text or tool-delta
            try:
                delta = chunk.choices[0].delta
            except (IndexError, AttributeError):
                continue
            content += getattr(delta, "content", None) or ""
            for tc in (getattr(delta, "tool_calls", None) or []):
                slot = calls.setdefault(getattr(tc, "index", 0), {"name": "", "args": ""})
                fn = getattr(tc, "function", None)
                if fn and getattr(fn, "name", None):
                    slot["name"] = fn.name
        total = time.time() - t0
        names = [c["name"] for c in calls.values() if c["name"]]
        return {"ok": True, "ttft_ms": round((ttft or total) * 1000, 1),
                "total_ms": round(total * 1000, 1), "route": _route_of(content, names),
                "tools": names, "reply": content.strip()[:120]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "err": str(e).splitlines()[0][:140], "total_ms": round((time.time() - t0) * 1000, 1)}


async def _bench_candidate(c: Candidate, reps: int) -> dict:
    from openai import AsyncOpenAI
    key = os.getenv(c.api_key_env, "")
    if not key:
        return {"label": c.label, "skipped": f"sin {c.api_key_env}"}
    ua = _BROWSER_UA if "aimlapi" in c.base_url else ""
    cli = AsyncOpenAI(api_key=key, base_url=c.base_url,
                      default_headers=({"User-Agent": ua} if ua else None))
    per_turn = []
    print(f"\n▶ {c.label}")
    for tid, text, expected, cat in TURNS:
        system, messages = _build_prompt(text)
        prompt_chars = len(system) + len(text)
        samples = []
        route = None
        reply = ""
        degenerate = False
        err = None
        for r in range(reps + 1):        # +1 = discard the 1st one (cold)
            res = await _one_call(cli, c.model, messages, c.reasoning_off, c.extra_body)
            if not res["ok"]:
                err = res["err"]
                break
            if r > 0:                     # discard the cold one
                samples.append(res)
            route = res["route"]
            reply = res["reply"]
        if err:
            per_turn.append({"turn": tid, "cat": cat, "expected": expected, "err": err})
            print(f"    {tid:11s} ✗ {err}")
            continue
        ttfts = [s["ttft_ms"] for s in samples]
        totals = [s["total_ms"] for s in samples]
        hit = (route == expected)
        # INTELLIGENCE: in intel turns, "getting it right" = NOT over-acting (staying in `chat`) AND not giving an
        # empty/garbage response. The spurious route (opening/searching when inappropriate) is the typical failure of the "dumb" model.
        reply_ok = len((reply or "").strip()) >= 8
        intel_ok = (cat == "intel") and hit and reply_ok
        rec = {"turn": tid, "cat": cat, "expected": expected, "route": route, "hit": hit,
               "reply_ok": reply_ok, "intel_ok": intel_ok, "prompt_chars": prompt_chars,
               "prompt_tokens_est": int(round(prompt_chars / 4)),
               "ttft_p50": round(statistics.median(ttfts), 0),
               "ttft_min": min(ttfts), "total_p50": round(statistics.median(totals), 0),
               "reply": reply}
        per_turn.append(rec)
        _mark = ("✓" if hit else "✗→" + route) if cat == "routing" else \
                ("🧠✓" if intel_ok else f"🧠✗ actuó={route}" if not hit else "🧠✗ resp-vacía")
        print(f"    {tid:11s} TTFT {rec['ttft_p50']:>6.0f}ms · total {rec['total_p50']:>6.0f}ms · "
              f"in≈{rec['prompt_tokens_est']}tok · ruta {route:11s} {_mark}")
    ok_turns = [t for t in per_turn if "err" not in t]
    routing = [t for t in ok_turns if t.get("cat") == "routing"]
    intel = [t for t in ok_turns if t.get("cat") == "intel"]
    if ok_turns:
        agg = {
            "label": c.label,
            # LATENCY (only from the "normal" routing turns, comparable with historical data)
            "ttft_p50_ms": round(statistics.median([t["ttft_p50"] for t in (routing or ok_turns)]), 0),
            "total_p50_ms": round(statistics.median([t["total_p50"] for t in (routing or ok_turns)]), 0),
            "routing_hits": sum(1 for t in routing if t["hit"]), "routing_total": len(routing),
            # INTELLIGENCE (separate from TTFT — this determines speed-versus-intelligence in reality)
            "intel_hits": sum(1 for t in intel if t["intel_ok"]), "intel_total": len(intel),
            "prompt_tokens_est": int(round(statistics.median([t["prompt_tokens_est"] for t in ok_turns]))),
            "turns": per_turn,
        }
    else:
        agg = {"label": c.label, "turns": per_turn, "all_failed": True}
    return agg


async def main() -> None:
    ap = argparse.ArgumentParser(description="Benchmark de modelos del FlashBrain (latencia ↔ inteligencia)")
    ap.add_argument("--reps", type=int, default=3, help="reps calientes por turno (descarta 1 fría extra)")
    ap.add_argument("--models", default="", help="lista separada por comas (default = shortlist)")
    ap.add_argument("--gemini-direct", action="store_true", help="añade Gemini por endpoint google-directo (thinking OFF)")
    ap.add_argument("--deepseek-nothink", action="store_true",
                    help="añade DeepSeek V4 Flash en modo NON-THINKING (thinking:disabled) — el modo apto para voz")
    args = ap.parse_args()

    model_ids = [m.strip() for m in args.models.split(",") if m.strip()] or DEFAULT_MODELS
    candidates = [_aimlapi(m) for m in model_ids]
    if args.gemini_direct:
        for m in model_ids:
            if "gemini" in m:
                candidates.append(_gemini_direct(m))
    if args.deepseek_nothink:
        # v4-flash defaults to THINKING (high latency/variation). For voice, NON-THINKING is useful: same model,
        # thinking:disabled. Anthropic-compatible and OpenAI-compatible APIs accept the `thinking` field (api-docs.deepseek.com).
        c = _aimlapi("deepseek/deepseek-v4-flash")
        candidates.append(Candidate(f"{c.label} (non-thinking)", c.model, c.base_url, c.api_key_env,
                                    extra_body={"thinking": {"type": "disabled"}}))

    print(f"═══ BENCHMARK FlashBrain · {len(candidates)} modelos · {args.reps} reps · {len(TURNS)} turnos ═══")
    print("(TTFT = 1er token; es lo que hace que la voz se sienta viva. La 1ª rep de cada turno se descarta como fría.)")

    results = []
    for c in candidates:
        results.append(await _bench_candidate(c, args.reps))

    # ── summary table ──
    print("\n\n═══ RESUMEN (ordenado por TTFT) ═══")
    print(f"{'modelo':40s} {'TTFT p50':>10s} {'total p50':>10s} {'routing':>9s} {'🧠 intel':>9s} {'in≈tok':>8s}")
    print("─" * 92)
    ranked = sorted([r for r in results if not r.get("skipped") and not r.get("all_failed")],
                    key=lambda r: r["ttft_p50_ms"])
    for r in ranked:
        print(f"{r['label']:40s} {r['ttft_p50_ms']:>8.0f}ms {r['total_p50_ms']:>8.0f}ms "
              f"{r['routing_hits']:>4d}/{r['routing_total']:<4d} "
              f"{r.get('intel_hits',0):>4d}/{r.get('intel_total',0):<4d} {r.get('prompt_tokens_est',0):>8d}")
    print("\nLatencia (TTFT) y ROUTING casi todos lo pasan → mira 🧠 intel: es lo que separa velocidad de "
          "INTELIGENCIA (introspección · no-alucinar · no-actuar-de-más · resolver contradicción).")
    for r in results:
        if r.get("skipped"):
            print(f"{r['label']:40s}   SALTADO ({r['skipped']})")
        elif r.get("all_failed"):
            errs = {t.get('err','?') for t in r['turns'] if 'err' in t}
            print(f"{r['label']:40s}   TODO FALLÓ ({'; '.join(list(errs)[:1])})")

    # ── save ──
    os.makedirs("tests/runs/agent", exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = f"tests/runs/agent/model_bench_{stamp}.json"
    with open(path, "w") as f:
        json.dump({"reps": args.reps, "turns": [t[0] for t in TURNS], "results": results}, f,
                  ensure_ascii=False, indent=2)
    print(f"\n✓ crudo → {path}")


if __name__ == "__main__":
    asyncio.run(main())
