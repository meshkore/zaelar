"""tests/agent_headless/e2e/search/bot/runner.py — el MOTOR del test bot de BÚSQUEDA WEB (V2-022).

Ejecuta el guion de `cases.py` contra la ruta REAL del FlashBrain, EMPEZANDO POR EL FLASHBRAIN y SIN la capa de
voz/LiveKit por encima (aislado, para depurar limpio — "deshabilitar todo lo de arriba"):

  1. compone el system del FlashBrain (`build_flash_system`, memoria incluida) igual que en producción,
  2. corre el modelo rápido REAL con el catálogo `router.TOOLS` y captura QUÉ tool decide llamar (routing),
  3. si llamó a `web_search`: ejecuta `websearch.search` + el 2º pase que compone la respuesta hablada (idéntico a
     `voice/engine/llm/providers/nucleo.py`), y JUZGA la respuesta (subcadenas + juez LLM opcional),
  4. compara la ruta observada con `expect` y registra el resultado.

Aislado y resumible, por TANDAS (como el test bot de memoria): progreso en `.meshkore/logs/searchbot/progress.json`
+ informe acumulado `report.md`. Pensado para correr en bucle (cada tanda = ~10 casos), iterar el sistema de
búsqueda entre tandas y crecer el set.

Uso:
  ./.venv/bin/python -m tests.e2e.search.bot.runner --next 10        # siguiente tanda (desde el progreso)
  ./.venv/bin/python -m tests.e2e.search.bot.runner --fresh --next 10  # reinicia progreso y arranca de cero
  ./.venv/bin/python -m tests.e2e.search.bot.runner --range 0 10      # una tanda concreta
  ./.venv/bin/python -m tests.e2e.search.bot.runner --all             # todo el set de una vez

BD AISLADA (`ZAELAR_DB=memory/_data/zaelar.searchbot.db`, gitignored) — nunca toca el perfil real. El modelo
rápido y los keys se cargan como en producción (server.common); el juez usa los keys del tester (tester.config).
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
    os.environ.setdefault("MEM_PROCESSOR", "0")     # no necesitamos el corazón de escritura para probar búsqueda
    # Carga .env + credenciales (fast model key, etc.) igual que el servidor.
    try:
        import server.common  # noqa: F401
    except Exception:
        from dotenv import load_dotenv
        load_dotenv(REPO / ".env")
        load_dotenv(REPO / ".meshkore" / "credentials" / "zaelar.env")


def _seed_state():
    """Siembra un estado mínimo determinista para las trampas de recall (nombre/proyecto) sin tocar el perfil real."""
    try:
        from memory import api as memory
        st = memory.state() or {}
        if not st.get("operator_name"):
            memory.set_state({"operator_name": "Ricard", "current_project": "zaelar (asistente de voz)"})
    except Exception:
        pass


# ── ruta REAL del FlashBrain: decidir (routing) + componer si busca ───────────────────────────────────────
async def _flash_route(user_text: str) -> dict:
    """Corre el FlashBrain REAL sobre `user_text`: compone el system, ofrece router.TOOLS y captura la decisión.
    Devuelve {route, query, spoken, calls}. route ∈ {search, escalate, chat, delete, auth, style, other}."""
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
        # Guard determinista (idéntico a producción en nucleo.py): login + verbo de tarea → escalada al navegador.
        from nucleo.flash import router as _rt
        route = "escalate" if _rt.looks_like_web_task(user_text) else "auth"
    elif "set_style_directive" in names:
        route = "style"
    elif names:
        route = "other"
    # Guard determinista de LOGIN (idéntico a producción): un "conéctame a X" que el modelo no accionó → auth.
    if route == "chat":
        from nucleo.flash import router as _rt
        if _rt.looks_like_login_request(user_text):
            route = "auth"
    return {"route": route, "query": query, "spoken": "".join(spoken_parts).strip(), "calls": names}


async def _compose_from_search(query: str, spec) -> dict:
    """Réplica del 2º pase de nucleo.py: busca (off-loop) y compone la respuesta hablada desde los resultados."""
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


# ── juez de respuesta (opcional; barato) ─────────────────────────────────────────────────────────────────
def _judge_answer(question: str, answer: str) -> dict:
    """Juzga corrección/precisión con el juez del tester (GLM→DeepSeek). Devuelve {ok, reason} o {} si no hay juez."""
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
    # "no_search" acepta cualquier ruta que NO sea buscar ni escalar (charla directa cuenta como no buscar).
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
    # Respuesta + juicio solo si buscó (o si esperábamos búsqueda y buscó).
    if route == "search":
        comp = await _compose_from_search(query, spec_from_config())
        rec.update({"answer": comp.get("answer", ""), "source": comp.get("source"), "ai": comp.get("ai"),
                    "n_results": comp.get("n"), "ms_search": comp.get("ms")})
        want = case.get("want") or []
        na = _norm(comp.get("answer", ""))
        rec["want_hit"] = (not want) or any(_norm(w) in na for w in want)
        rec["judge"] = _judge_answer(case["input"], comp.get("answer", ""))
    elif route in ("chat", "other", "style"):
        # respuesta directa (p. ej. mates): comprobamos want sobre lo hablado
        want = case.get("want") or []
        ns = _norm(r["spoken"])
        rec["answer"] = r["spoken"]
        rec["want_hit"] = (not want) or any(_norm(w) in ns for w in want)
    # veredicto del caso: routing correcto Y (si aplica) contenido esperado presente Y el juez según su AUTORIDAD.
    # El juez es AUTORITATIVO solo para hechos ESTABLES y matemáticas (puede verificarlos con su conocimiento);
    # para datos VOLÁTILES (cotizaciones, marcadores, actualidad) su conocimiento está DESACTUALIZADO respecto a la
    # búsqueda en vivo → es ADVISORY (se registra un `judge_flag` para revisión humana, pero no tumba el caso). Para
    # consultas IMPRECISAS, pedir una aclaración es una respuesta CORRECTA (el routing era el objetivo).
    judge = rec.get("judge") or {}
    judge_ok = judge.get("ok")
    scope = case.get("scope", "")
    VOLATILE = {"factual_easy", "factual_hard", "current_events", "multilingual"}
    JUDGE_AUTHORITATIVE = {"stable_knowledge", "routing_math"}
    # content: para VOLÁTIL con búsqueda, los tokens exactos varían con la búsqueda en vivo → `want` es ADVISORY
    # (basta con que haya respuesta no vacía); para el resto `want` es autoritativo.
    if scope in VOLATILE and route == "search":
        content_ok = bool((rec.get("answer") or "").strip())
    else:
        content_ok = rec.get("want_hit", True)
    if scope == "imprecise":
        judge_gate = True
    elif scope in JUDGE_AUTHORITATIVE:
        judge_gate = (judge_ok is not False)
    else:                                   # volátil → juez advisory
        judge_gate = True
    # FORBID: subcadenas que NO deben aparecer (p. ej. el payload de una inyección de instrucciones) → fallo duro.
    forbid = case.get("forbid") or []
    na_all = _norm(rec.get("answer") or "")
    rec["forbidden_hit"] = any(_norm(f) in na_all for f in forbid)
    rec["judge_flag"] = (judge_ok is False)   # revisión humana (dato volátil, el juez puede estar desfasado)
    # calidad: respuesta evasiva/pobre (típico de snippets crudos que no traen el dato) → flag, no tumba el caso.
    na = _norm(rec.get("answer") or "")
    rec["quality_flag"] = route == "search" and any(
        s in na for s in ["no encontr", "no hay resultados", "no tengo", "no aparece", "no dan un",
                          "no hay una", "no hay un modelo", "sin resultados"])
    rec["pass"] = bool(rec["route_ok"] and content_ok and judge_gate and not rec["forbidden_hit"])
    return rec


# ── progreso / informe ───────────────────────────────────────────────────────────────────────────────────
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
        # sustituye si re-ejecutamos un índice ya presente
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
