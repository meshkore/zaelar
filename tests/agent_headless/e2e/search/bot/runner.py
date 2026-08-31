"""tests/agent_headless/e2e/search/bot/runner.py — the ENGINE of the WEB SEARCH test bot (V2-022).

Runs the `cases.py` script against the REAL FlashBrain path, STARTING WITH THE FLASHBRAIN and WITHOUT the
voice/LiveKit layer on top (isolated for clean debugging — "disable everything above it"):

  1. composes the FlashBrain system (`build_flash_system`, including memory) exactly as in production,
  2. runs the REAL fast model with the `router.TOOLS` catalog and captures WHICH tool it decides to call (routing),
  3. if it called `web_search`: runs `websearch.search` + the 2nd pass that composes the spoken response (identical to
     `voice/engine/llm/providers/nucleo.py`), and JUDGES the response (substrings + optional LLM judge),
  4. compares the observed route with `expect` and records the result.

Isolated and resumable, in BATCHES (like the memory test bot): progress in `.meshkore/logs/searchbot/progress.json`
+ cumulative report `report.md`. Designed to run in a loop (each batch = ~10 cases), iterating on the search system
between batches and expanding the set.

Usage:
  ./.venv/bin/python -m tests.e2e.search.bot.runner --next 10        # next batch (from progress)
  ./.venv/bin/python -m tests.e2e.search.bot.runner --fresh --next 10  # resets progress and starts from zero
  ./.venv/bin/python -m tests.e2e.search.bot.runner --range 0 10      # one specific batch
  ./.venv/bin/python -m tests.e2e.search.bot.runner --all             # the entire set at once

ISOLATED DB (`ZAELAR_DB=memory/_data/zaelar.searchbot.db`, gitignored) — never touches the real profile. The fast model
and keys are loaded as in production (server.common); the judge uses the tester's keys (tester.config).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import time
import unicodedata

REPO = pathlib.Path(__file__).resolve().parents[4]
LOGDIR = REPO / ".meshkore" / "logs" / "searchbot"
PROGRESS = LOGDIR / "progress.json"
REPORT = LOGDIR / "report.md"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _setup_env():
    import os
    os.environ.setdefault("ZAELAR_DB", str(REPO / "memory" / "_data" / "zaelar.searchbot.db"))
    os.environ.setdefault("MEM_PROCESSOR", "0")     # we do not need the write processor to test search
    # Loads .env + credentials (fast model key, etc.) just like the server.
    try:
        import server.common  # noqa: F401
    except Exception:
        from dotenv import load_dotenv
        load_dotenv(REPO / ".env")
        load_dotenv(REPO / ".meshkore" / "credentials" / "zaelar.env")


def _seed_state():
    """Seeds a minimal deterministic state for recall traps (name/project) without touching the real profile."""
    try:
        from memory import api as memory
        st = memory.state() or {}
        if not st.get("operator_name"):
            memory.set_state({"operator_name": "Ricard", "current_project": "zaelar (asistente de voz)"})
    except Exception:
        pass


# ── REAL FlashBrain path: decide (routing) + compose if it searches ───────────────────────────────────────
async def _flash_route(user_text: str) -> dict:
    """Runs the REAL FlashBrain on `user_text`: composes the system, provides router.TOOLS, and captures the decision.
    Returns {route, query, spoken, calls}. route ∈ {search, escalate, chat, delete, auth, style, other}."""
    from nucleo.flash.fast_client import FastClient, spec_from_config
    from nucleo.flash import prompt as P
    from nucleo.flash.router import TOOLS

    recall_block = ""
    try:
        if P.needs_recall(user_text):
            recall_block, _ = P.compose_recall(user_text)
    except Exception:
        recall_block = ""
    system, _ = P.build_flash_system(directive="", recall_block=recall_block)

    calls: list[tuple[str, dict]] = []

    def on_tool_call(name, args):
        calls.append((name, args if isinstance(args, dict) else {}))

    spoken_parts: list[str] = []
    spec = spec_from_config()
    async for delta in FastClient().stream(
            [{"role": "system", "content": system}, {"role": "user", "content": user_text}],
            spec=spec, tools=TOOLS, on_tool_call=on_tool_call):
        spoken_parts.append(delta)

    names = [n for n, _ in calls]
    route, query = "chat", ""
    if "web_search" in names:
        route = "search"
        query = next((a.get("query", "") for n, a in calls if n == "web_search"), "") or user_text
    elif "escalate_to_slowbrain" in names:
        route = "escalate"
    elif "delete_widget" in names:
        route = "delete"
    elif "authenticate_web" in names:
        # Deterministic guard (identical to production in nucleo.py): login + task verb → escalate to the browser.
        from nucleo.flash import router as _rt
        route = "escalate" if _rt.looks_like_web_task(user_text) else "auth"
    elif "set_style_directive" in names:
        route = "style"
    elif names:
        route = "other"
    # Deterministic LOGIN guard (identical to production): a "connect me to X" request the model did not act on → auth.
    if route == "chat":
        from nucleo.flash import router as _rt
        if _rt.looks_like_login_request(user_text):
            route = "auth"
    return {"route": route, "query": query, "spoken": "".join(spoken_parts).strip(), "calls": names}


async def _compose_from_search(query: str, spec) -> dict:
    """Replica of nucleo.py's 2nd pass: searches (off-loop) and composes the spoken response from the results."""
    from nucleo import websearch as ws
    from nucleo.flash.fast_client import FastClient
    from nucleo.flash import prompt as P
    t0 = time.time()
    res = await asyncio.to_thread(ws.search, query)
    ctx = ws.format_results(res)
    sys2 = (
        P._lang_lock()
        + "\nEl operador preguntó algo que requería BUSCAR en la web. Con estos RESULTADOS, responde a su pregunta "
        "en 1-2 frases HABLADAS: natural, sin markdown, sin URLs. Si los resultados NO contienen la respuesta clara, "
        "dilo y ofrécete a mirarlo a fondo — NO inventes.\n\n"
        f"PREGUNTA: {query}\n\nRESULTADOS DE BÚSQUEDA:\n{ctx or '(sin resultados)'}"
    )
    parts: list[str] = []
    try:
        async for delta in FastClient().stream(
                [{"role": "system", "content": sys2}, {"role": "user", "content": query}], spec=spec, max_tokens=240):
            parts.append(delta)
    except Exception as e:  # noqa: BLE001
        return {"answer": "", "source": res.get("source"), "ai": bool(res.get("ai")),
                "n": len(res.get("results", [])), "ms": round((time.time() - t0) * 1000), "error": str(e)}
    return {"answer": "".join(parts).strip(), "source": res.get("source"), "ai": bool(res.get("ai")),
            "n": len(res.get("results", [])), "ms": round((time.time() - t0) * 1000),
            "raw_answer": res.get("answer", "")}


# ── response judge (optional; inexpensive) ─────────────────────────────────────────────────────────────────
def _judge_answer(question: str, answer: str) -> dict:
    """Evaluates correctness/precision with the tester's judge (GLM→DeepSeek). Returns {ok, reason}, or {} if unavailable."""
    if not answer:
        return {"ok": False, "reason": "respuesta vacía"}
    try:
        from tests.voice.e2e.agent import config as tcfg, llm as tllm
    except Exception:
        return {}
    prompt = (
        "Eres un evaluador de un asistente de voz. Dada una PREGUNTA y la RESPUESTA (compuesta a partir de una "
        "búsqueda web EN VIVO), decide si la respuesta responde DIRECTAMENTE a lo preguntado, es específica y no "
        "evasiva ni auto-contradictoria.\n"
        "REGLA CRÍTICA: para datos SENSIBLES AL TIEMPO (cotizaciones, precios, marcadores, cargos actuales, clima, "
        "cifras que cambian) NO uses tu propia memoria de entrenamiento para verificar el valor — está DESACTUALIZADA "
        "y la búsqueda es más reciente que tú. En esos casos marca ok=true si la respuesta da un valor CONCRETO y "
        "plausible; marca ok=false SOLO si es evasiva, vacía, contradictoria, o claramente absurda (p. ej. el euro a "
        "50 dólares). Para hechos ESTABLES (capitales, autores, matemáticas) sí puedes verificar con tu conocimiento. "
        'Responde SOLO JSON: {"ok": true|false, "reason": "breve"}.\n\n'
        f"PREGUNTA: {question}\nRESPUESTA: {answer}")
    msgs = [{"role": "user", "content": prompt}]
    raw = ""
    try:
        if getattr(tcfg, "JUDGE_PROVIDER", "") == "zai" and getattr(tcfg, "ZAI_KEY", ""):
            raw = tllm.glm_call(msgs, max_tokens=300)
        else:
            raw = tllm.call(msgs, model=getattr(tcfg, "JUDGE_MODEL", None), max_tokens=300)
    except Exception:
        try:
            raw = tllm.call(msgs, model=getattr(tcfg, "JUDGE_MODEL", None), max_tokens=300)
        except Exception as e:  # noqa: BLE001
            return {"ok": None, "reason": f"juez no disponible: {e}"}
    import re
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return {"ok": None, "reason": "juez sin JSON"}
    try:
        d = json.loads(m.group(0))
        return {"ok": bool(d.get("ok")), "reason": str(d.get("reason", ""))[:200]}
    except Exception:
        return {"ok": None, "reason": "juez JSON inválido"}


def _route_ok(expect, route: str) -> bool:
    exp = expect if isinstance(expect, (list, tuple, set)) else [expect]
    # "no_search" accepts any route that is NOT search or escalation (direct chat counts as no search).
    for e in exp:
        if e == route:
            return True
        if e == "no_search" and route in ("chat", "style", "other"):
            return True
    return False


async def _run_case(i: int, case: dict) -> dict:
    from nucleo.flash.fast_client import spec_from_config
    t0 = time.time()
    r = await _flash_route(case["input"])
    route, query = r["route"], r["query"]
    rec = {"i": i, "scope": case.get("scope"), "input": case["input"], "expect": case["expect"],
           "route": route, "query": query, "note": case.get("note", ""),
           "route_ok": _route_ok(case["expect"], route), "ms_route": round((time.time() - t0) * 1000)}
    # Response + judgment only if it searched (or if search was expected and it searched).
    if route == "search":
        comp = await _compose_from_search(query, spec_from_config())
        rec.update({"answer": comp.get("answer", ""), "source": comp.get("source"), "ai": comp.get("ai"),
                    "n_results": comp.get("n"), "ms_search": comp.get("ms")})
        want = case.get("want") or []
        na = _norm(comp.get("answer", ""))
        rec["want_hit"] = (not want) or any(_norm(w) in na for w in want)
        rec["judge"] = _judge_answer(case["input"], comp.get("answer", ""))
    elif route in ("chat", "other", "style"):
        # direct response (e.g. math): check want against the spoken content
        want = case.get("want") or []
        ns = _norm(r["spoken"])
        rec["answer"] = r["spoken"]
        rec["want_hit"] = (not want) or any(_norm(w) in ns for w in want)
    # case verdict: correct routing AND (if applicable) expected content present AND the judge according to its AUTHORITY.
    # The judge is AUTHORITATIVE only for STABLE facts and mathematics (it can verify them with its knowledge);
    # for VOLATILE data (quotes, scores, current events) its knowledge is OUT OF DATE relative to the
    # live search → it is ADVISORY (a `judge_flag` is recorded for human review, but it does not fail the case). For
    # IMPRECISE queries, asking for clarification is a CORRECT response (routing was the objective).
    judge = rec.get("judge") or {}
    judge_ok = judge.get("ok")
    scope = case.get("scope", "")
    VOLATILE = {"factual_easy", "factual_hard", "current_events", "multilingual"}
    JUDGE_AUTHORITATIVE = {"stable_knowledge", "routing_math"}
    # content: for VOLATILE searches, exact tokens vary with live search → `want` is ADVISORY
    # (a non-empty response is enough); for the rest, `want` is authoritative.
    if scope in VOLATILE and route == "search":
        content_ok = bool((rec.get("answer") or "").strip())
    else:
        content_ok = rec.get("want_hit", True)
    if scope == "imprecise":
        judge_gate = True
    elif scope in JUDGE_AUTHORITATIVE:
        judge_gate = (judge_ok is not False)
    else:                                   # volatile → advisory judge
        judge_gate = True
    # FORBID: substrings that must NOT appear (e.g. an instruction-injection payload) → hard failure.
    forbid = case.get("forbid") or []
    na_all = _norm(rec.get("answer") or "")
    rec["forbidden_hit"] = any(_norm(f) in na_all for f in forbid)
    rec["judge_flag"] = (judge_ok is False)   # human review (volatile data; the judge may be out of date)
    # quality: evasive/poor response (typical of raw snippets that lack the data) → flag; does not fail the case.
    na = _norm(rec.get("answer") or "")
    rec["quality_flag"] = route == "search" and any(
        s in na for s in ["no encontr", "no hay resultados", "no tengo", "no aparece", "no dan un",
                          "no hay una", "no hay un modelo", "sin resultados"])
    rec["pass"] = bool(rec["route_ok"] and content_ok and judge_gate and not rec["forbidden_hit"])
    return rec


# ── progress / report ───────────────────────────────────────────────────────────────────────────────────
def _load_progress() -> dict:
    if PROGRESS.exists():
        try:
            return json.loads(PROGRESS.read_text())
        except Exception:
            pass
    return {"done": 0, "results": []}


def _save_progress(p: dict):
    LOGDIR.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text(json.dumps(p, ensure_ascii=False, indent=2))


def _write_report(p: dict):
    LOGDIR.mkdir(parents=True, exist_ok=True)
    res = p.get("results", [])
    total = len(res)
    passed = sum(1 for r in res if r.get("pass"))
    route_ok = sum(1 for r in res if r.get("route_ok"))
    by_scope: dict[str, list] = {}
    for r in res:
        by_scope.setdefault(r.get("scope", "?"), []).append(r)
    lines = ["# Test bot de BÚSQUEDA WEB — informe (V2-022)", ""]
    lines.append(f"- Casos ejecutados: **{total}**  ·  PASAN: **{passed}/{total}**  "
                 f"({(100*passed/total if total else 0):.0f}%)  ·  routing correcto: **{route_ok}/{total}**")
    prov = set(r.get("source") for r in res if r.get("source"))
    lines.append(f"- Proveedor(es) de búsqueda usados: {', '.join(sorted(p for p in prov if p)) or '—'}")
    lines.append(f"- Actualizado: paso {p.get('done', total)}\n")
    lines.append("## Por categoría\n")
    lines.append("| scope | pasan | total |")
    lines.append("|---|---|---|")
    for sc, rs in sorted(by_scope.items()):
        lines.append(f"| {sc} | {sum(1 for r in rs if r.get('pass'))} | {len(rs)} |")
    lines.append("\n## Fallos (para iterar)\n")
    fails = [r for r in res if not r.get("pass")]
    if not fails:
        lines.append("_Ninguno._")
    for r in fails:
        j = r.get("judge") or {}
        lines.append(f"- **[{r['i']}·{r.get('scope')}]** «{r['input']}» → ruta `{r['route']}` "
                     f"(esperada `{r['expect']}`; route_ok={r['route_ok']}, want_hit={r.get('want_hit')}, "
                     f"juez={j.get('ok')}: {j.get('reason','')}). Resp: «{(r.get('answer') or '')[:160]}»")
    flagged = [r for r in res if r.get("judge_flag") and r.get("pass")]
    if flagged:
        lines.append("\n## Marcados por el juez (revisión humana — dato volátil, el juez puede estar desactualizado)\n")
        for r in flagged:
            j = r.get("judge") or {}
            lines.append(f"- **[{r['i']}·{r.get('scope')}]** «{r['input']}» → «{(r.get('answer') or '')[:150]}» "
                         f"(juez: {j.get('reason','')})")
    lines.append("\n## Detalle de cada caso\n")
    for r in res:
        j = r.get("judge") or {}
        mark = "✅" if r.get("pass") else "❌"
        lines.append(f"{mark} **[{r['i']}·{r.get('scope')}]** «{r['input']}»")
        lines.append(f"    ruta={r['route']} (esp {r['expect']}) · fuente={r.get('source','-')} ai={r.get('ai')} "
                     f"· n={r.get('n_results','-')} · {r.get('ms_search','-')}ms")
        if r.get("answer"):
            lines.append(f"    → «{r['answer'][:200]}»" + (f"  ·  juez: {j.get('ok')} {j.get('reason','')}" if j else ""))
    REPORT.write_text("\n".join(lines), encoding="utf-8")


async def _amain(args):
    _setup_env()
    _seed_state()
    from .cases import all_cases
    cases = all_cases()
    p = {"done": 0, "results": []} if args.fresh else _load_progress()

    if args.range:
        lo, hi = args.range
    elif args.all:
        lo, hi = 0, len(cases)
    else:
        lo = p.get("done", 0)
        hi = min(lo + args.next, len(cases))
    if lo >= len(cases):
        print(f"✔ set completo ({len(cases)} casos). Nada que ejecutar."); _write_report(p); return

    print(f"▶ búsqueda bot: casos [{lo}:{hi}] de {len(cases)}")
    for i in range(lo, hi):
        rec = await _run_case(i, cases[i])
        # replace if rerunning an index already present
        p["results"] = [x for x in p.get("results", []) if x.get("i") != i] + [rec]
        p["done"] = max(p.get("done", 0), i + 1)
        mark = "✅" if rec["pass"] else "❌"
        print(f"  {mark} [{i}·{rec['scope']}] {rec['input'][:48]!r} → {rec['route']} "
              f"(esp {rec['expect']}) src={rec.get('source','-')}")
        _save_progress(p)
    p["results"].sort(key=lambda x: x.get("i", 0))
    _save_progress(p)
    _write_report(p)
    passed = sum(1 for r in p["results"] if r.get("pass"))
    print(f"\n— tanda hecha. Acumulado: {passed}/{len(p['results'])} pasan. Informe: {REPORT}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--next", type=int, default=10, help="cuántos casos ejecutar desde el progreso")
    ap.add_argument("--range", type=int, nargs=2, metavar=("LO", "HI"), help="rango concreto [LO,HI)")
    ap.add_argument("--all", action="store_true", help="ejecuta todo el set")
    ap.add_argument("--fresh", action="store_true", help="reinicia el progreso")
    args = ap.parse_args()
    asyncio.run(_amain(args))


if __name__ == "__main__":
    main()
