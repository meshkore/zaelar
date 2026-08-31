"""Turn scenario runs + judge verdicts into a report. Adapted from tests/voice/e2e/agent/judge/report.py —
same two-file convention (.md for humans/agents, .json for machines) under tests/runs/use_cases/."""
from __future__ import annotations

import json
from pathlib import Path

_SEV = {"alta": 0, "media": 1, "baja": 2}


def build(results: list[dict], stamp: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    improvements: list[dict] = []
    for r in results:
        v = r.get("verdict", {})
        sev = min((_SEV.get(f.get("gravedad", "baja"), 2) for f in v.get("findings", [])), default=2)
        for imp in v.get("improvements", []):
            improvements.append({**imp, "scenario": r["scenario"], "_sev": sev})
    improvements.sort(key=lambda x: x["_sev"])

    lines = [f"# zaelar — informe de casos de uso ({stamp})", "",
             "Generado por el tester de casos de uso: el usuario lo simula un modelo con razonamiento, "
             "pidiendo las cosas como una persona real (ambiguo, corrige sobre la marcha). Se juzga a ZAELAR "
             "por lo que realmente pasó en el sistema (informe de mecanismo), no solo por lo que dijo.", "",
             "## Resumen por escenario", "",
             "| escenario | tier | overall | turnos | señales faltantes | veredicto |",
             "|---|---|---|---|---|---|"]
    for r in results:
        v = r.get("verdict", {})
        mech = r.get("run", {}).get("mechanism_report", {})
        missing = ", ".join(mech.get("missing_signals", [])) or "—"
        lines.append(f"| {r['scenario']} | {r.get('tier','?')} | {v.get('overall','—')}/5 | "
                     f"{len(r.get('run', {}).get('transcript', []))} | {missing} | "
                     f"{(v.get('veredicto','') or '')[:90]} |")

    lines += ["", "## Mejoras propuestas (priorizadas)", ""]
    if improvements:
        for i, imp in enumerate(improvements, 1):
            lines.append(f"{i}. **[{imp['scenario']}] {imp.get('area','?')}** — {imp.get('cambio','')}")
            lines.append(f"   · _por qué_: {imp.get('porque','')}")
    else:
        lines.append("_(sin mejoras propuestas)_")

    lines += ["", "## Detalle por escenario", ""]
    for r in results:
        v = r.get("verdict", {})
        run = r.get("run", {})
        mech = run.get("mechanism_report", {})
        lines.append(f"### {r['scenario']} (tier {r.get('tier','?')}, canal {r.get('channel','')})")
        sc = v.get("scores", {})
        if sc:
            lines.append("scores: " + ", ".join(f"{k} {val}" for k, val in sc.items())
                         + f"  · juez: {v.get('_judge_model','?')}")
        if r.get("video"):
            # V2-464 — the round's video, alongside the session and its flows: what the user would have seen.
            lines.append(f"🎥 vídeo: {r['video']}")
        lines.append(f"informe de mecanismo: familias observadas = {mech.get('families_observed', [])}, "
                     f"esperadas = {mech.get('expected_signals', [])}, "
                     f"faltantes = {mech.get('missing_signals', []) or '(ninguna)'}")
        if mech.get("navegador_task_id"):
            nt = mech.get("navegador_task", {})
            lines.append(f"tarea de navegador {mech['navegador_task_id']}: status={nt.get('status','?')}, "
                         f"awaiting_login={nt.get('awaiting_login', False)}, "
                         f"resultados={len((nt.get('results') or {}).get('items', []) or [])}")
        # The SHEET, separate from the card and ALWAYS — it is the surface the operator looks at, and with V2-257 it becomes
        # the only one that stores findings. “I did not look at it” cannot be read the same as “it was empty.”
        sh = mech.get("results_sheet") or {}
        if not sh.get("read"):
            lines.append("hoja de resultados: NO se pudo leer (no es lo mismo que vacía)")
        else:
            _boxes = sh.get("boxes") or []
            lines.append(f"hoja de resultados: {sh.get('n_named', 0)} candidato(s) con nombre "
                         f"de {sh.get('n_items', 0)} fila(s) · {sh.get('n_backed', 0)} con enlace/fuente"
                         + (f" · pestaña Fuentes: {sh['n_sites_reported']} sitio(s)"
                            if sh.get("n_sites_reported") else "")
                         + (f" · leída en {', '.join(_boxes)}" if _boxes and _boxes != ["results"] else "")
                         + (f" · {', '.join(sh.get('titles') or [])}" if sh.get("titles") else ""))
            # EACH BOX SEPARATELY when there is more than one: the total does not say whether THIS task was served —
            # the neighboring box may contain its own results. This is the line separating “did not deliver” from
            # “delivered in its place while the reader was looking somewhere else.”
            _pb = sh.get("per_box") or []
            if len(_pb) > 1:
                lines.append("   por encargo: " + " · ".join(
                    f"{b.get('id')}: {b.get('n_items', 0)} fila(s) «{b.get('title') or ''}»" for b in _pb))
        # ONE BOX PER TASK. Printed only if there was at least one opening: for a single-task case it says
        # nothing that the line above does not already say, while for two tasks it is the line that decides the verdict.
        si = mech.get("sheet_instances") or {}
        if si.get("n_opens"):
            line = (f"hojas de resultados ABIERTAS: {si.get('n_sheets', 0)} caja(s) para "
                    f"{si.get('n_errands', 0)} encargo(s) · {si.get('n_opens', 0)} apertura(s)"
                    + (f" · {', '.join(si.get('ids') or [])}" if si.get("ids") else ""))
            if si.get("shared"):
                line += "  ⚠️ DOS ENCARGOS COMPARTIERON CAJA (la regla es una hoja por búsqueda)"
            lines.append(line)
        # CARDS THAT ARE LEFT OVER. `observed=False` stays silent on purpose: with no canvas attached there
        # was nothing to look at, and printing "0 ghosts" there would assert a check that never ran.
        gw = mech.get("ghost_widgets") or {}
        if gw.get("observed"):
            if gw.get("ghosts"):
                which = ", ".join(f"{g['id']} (junto a {', '.join(g.get('alongside') or [])})"
                                  for g in gw["ghosts"])
                lines.append(f"⚠️ TARJETA(S) FANTASMA en el canvas: {which} — se abrió la pieza BASE encima de "
                             f"su propia instancia, vacía. Último canvas: {', '.join(gw.get('last') or [])}")
            else:
                lines.append(f"canvas limpio: {gw.get('max_cards', 0)} tarjeta(s) como mucho, ninguna sin dueño")
        # THE MECHANISM NUMBERS, in the report that is READ and not only in the JSON. Until 2026-08-21, each
        # of these was extracted manually with a standalone script and pasted into a message: it worked while
        # someone was present to do it, and did not survive a handoff. The agent fixing the issue opens this
        # file, so this is where they need to be.
        for line in _mechanism_numbers(mech):
            lines.append(line)
        wd = run.get("watchdog_log", [])
        if wd:
            lines.append(f"watchdog: {len(wd)} veredicto(s) — " +
                         "; ".join(f"{w['health']}/{w['action']}" for w in wd))
        for f in v.get("findings", []):
            lines.append(f"- [{f.get('gravedad','?')}] {f.get('turno','')}: {f.get('problema','')}")
        for t in run.get("transcript", [])[:16]:
            lines.append(f"    {t['who']:7} {(t.get('text') or '(sin respuesta)')[:100]}")
        lines.append("")

    md = out_dir / f"report_{stamp}.md"
    md.write_text("\n".join(lines), encoding="utf-8")
    js = out_dir / f"report_{stamp}.json"
    js.write_text(json.dumps({"stamp": stamp, "results": results, "improvements": improvements},
                             ensure_ascii=False, indent=2), encoding="utf-8")
    return md


def _mechanism_numbers(mech: dict) -> list[str]:
    """The figures that determine WHO a failure belongs to, one per line and only when there is something to report.

    Each one arose from a defect that this harness misattributed before it existed: `worker_health` because
    “4 launched, 0 ok” was read as four failures when three were still working; `worker_deaths` because the
    cause of an entire family of cases was in correlating the warehouse with the log and no one could see it;
    `search_returns` because the search responded correctly but reached no one; `quiescence` because reading
    too early turns “it has not finished” into “it has failed.”
    """
    out: list[str] = []
    # V2-362 — THE CLOCK, IN THE REPORT. `sheet_timing` has been calculated since V2-300 and refined in V2-355, but it was not
    # printed anywhere: the judge receives it in the JSON, but whoever reads the report —a human or the
    # agent fixing the case— could not see the number. A measurement without a reader is a decision without
    # a caller: it exists and changes nothing.
    #
    # And it is THE number behind the operator's complaint (“a search takes one minute, two or three at most”):
    # how long the task takes to put its first row in front of the user. It is stated WITH the clock used, because the
    # loose one (“first write” by the worker, which may be its plan) and the strict one (the browser intake,
    # which contains real candidates) do not measure the same thing — and confusing them produced the invented 130.8 s
    # of “retention” that V2-355 eliminated.
    _st = mech.get("sheet_timing") or {}
    _t0, _named, _lag = _st.get("sheet_ms"), _st.get("sheet_named_ms"), _st.get("delivery_lag_s")
    if _t0 and _named:
        out.append(f"⏱ primera fila de candidatos: {round((_named - _t0) / 1000.0, 1)}s desde que se "
                     f"abrió la hoja"
                     + (f" · el turno los nombró {_lag}s después de que existieran"
                        if _lag is not None else "")
                     + (f" · reloj: {_st['delivery_clock']}" if _st.get("delivery_clock") else ""))
    elif _t0:
        out.append("⏱ primera fila de candidatos: NUNCA llegó (la hoja se abrió y el intake no escribió)")
    wh = mech.get("worker_health") or {}
    if wh.get("spawned"):
        bits = [f"{wh['spawned']} lanzado(s)", f"{wh.get('ok', 0)} ok"]
        if wh.get("errored"):
            bits.append(f"**{wh['errored']} con ERROR**")
        if wh.get("relayed"):
            bits.append(f"{wh['relayed']} relevado(s) de proveedor (NO es una muerte)")
        if wh.get("still_running"):
            bits.append(f"{wh['still_running']} seguía(n) trabajando al acabar la conversación")
        if wh.get("cancelled"):
            bits.append(f"{wh['cancelled']} cancelado(s) al cerrar la ronda")
        out.append("workers: " + " · ".join(bits))
    pj = mech.get("page_journey") or {}
    if pj.get("read") and pj.get("n_pages"):
        _ruta = " → ".join(f"{(p.get('title') or '?')[:34]}" for p in (pj.get("pages") or [])[:6])
        out.append(f"recorrido del navegador: {pj['n_pages']} página(s) · {_ruta}"
                   + ("…" if pj["n_pages"] > 6 else ""))
    if pj.get("n_walls"):
        _m = "; ".join(f"{(w.get('why') or '?')}: {(w.get('title') or '')[:30]}" for w in pj["walls"][:3])
        # STATED SEPARATELY from the rest: `found: 0` with a wall in front does not mean the same as without one, and
        # mixing it with delivery numbers is how a world-side blockage gets read as a product failure.
        out.append(f"⛔ **{pj['n_walls']} página(s) nos cerraron la puerta**: {_m} — un «no encontró nada» "
                   f"con esto delante puede ser «no le dejaron entrar»")
    dup = mech.get("duplicate_errands") or {}
    # A CONTINUATION is counted, with its reason, and NOT as a dedup failure: the token cost is real and
    # must be visible, but calling it a duplicate sends people to inspect a mechanism that behaved correctly (V2-238/V2-117).
    for c in (dup.get("continuations") or [])[:3]:
        out.append(f"· un worker MÁS por continuación del mismo encargo — {c.get('why')}: paga tokens dos "
                   f"veces, pero NO es un duplicado ni un fallo del dedup")
    # `g["n"]` COUNTS ESCALATION REQUESTS with the same text (`text_source: escalate.requested`), not workers.
    # Calling them “workers” invented a fact, and invented it alongside its own refutation: measured in
    # `cheapest-monitor__us` (2026-08-30), the report said “2 workers for ONE task … each is paid in full”
    # with `worker_health.spawned: 1` and `duplicate_errands.n_spawned: 1` in the same block. One worker was born. It was not
    # paid for twice. The accusation reached a task before dev-main dismantled it by reading the set's database
    # — meaning the instrument consumed another agent's time.
    #
    # `n_spawned` belongs to the window's aggregate, so as a bound it is CONSERVATIVE: if a group reports more
    # requests than workers born during the entire round, those requests cannot have been workers. And the gap
    # is not an accounting detail — it is the finding: an escalation that opens its sheet onscreen but never comes to life
    # leaves a box waiting for work that no one started.
    _nacidos = dup.get("n_spawned")
    for g in (dup.get("groups") or [])[:3]:
        _bar, _met = g.get("engine_bar"), g.get("engine_metric") or "contención"
        _bar_txt = f"{_met} del motor {g.get('max_sim')} ≥ {_bar}" if _bar else "sin poder leer la vara del motor"
        _how = (f"el dedup NO disparó ({_bar_txt})" if g.get("over_engine_bar")
                else f"reformulado — el motor lo ve a {g.get('max_sim')}, por debajo de su {_bar}")
        _n = g.get("n")
        if isinstance(_nacidos, int) and isinstance(_n, int) and _n > _nacidos:
            out.append(f"⚠️ **{_n} escaladas con el MISMO texto y solo {_nacidos} worker(s) NACIDO(S)** · "
                       f"contención {g.get('min_sim')}–{g.get('max_sim')} · {_how}: «{g.get('goal')}» — NO se "
                       f"paga dos veces (solo corrió {_nacidos}); lo que hay que mirar son las "
                       f"{_n - _nacidos} escalada(s) que no llegaron a nacer y qué dejaron en pantalla")
        else:
            out.append(f"⚠️ **{_n} workers para UN encargo** · contención {g.get('min_sim')}–"
                       f"{g.get('max_sim')} · {_how}: «{g.get('goal')}» — se paga entero cada vez y cada uno "
                       f"abre su propia hoja")
    if (dup.get("groups") or []) and not dup.get("continuations_visible"):
        out.append("  ⚠️ leído del `goal` del spawn, que NO dice de dónde viene: un RELEVO de proveedor sale "
                   "aquí como duplicado y no se puede distinguir")
    wdz = mech.get("worker_deaths") or {}
    if wdz.get("shared_sessions"):
        for sid, who in list(wdz["shared_sessions"].items())[:2]:
            out.append(f"⚠️ sesión nativa COMPARTIDA «{sid}» por los workers {', '.join(who)} — "
                       f"murieron {wdz.get('dead_resuming')} de {wdz.get('resuming')} de los que reanudaron, "
                       f"frente a {wdz.get('dead_fresh')} de {wdz.get('fresh')} de los que abrieron sesión propia")
    if wdz.get("lifetimes_ms"):
        quick = {w: round(ms) for w, ms in wdz["lifetimes_ms"].items() if ms and ms < 2000}
        if quick:
            out.append(f"murieron en menos de 2 s: {quick} (ms) — una búsqueda no dura eso")
    sr = mech.get("search_returns") or {}
    if sr.get("queries"):
        # V2-378 — the warning is valid only if SOME result arrived while the conversation was open. If all arrived
        # after the last turn, there was no one to push them to, and saying “none were pushed to it” accuses the mechanism
        # of an impossible delivery failure — the same care as the line for the engine that is still working.
        _tarde = int(sr.get("returns_after_last_turn") or 0)
        _a_tiempo = max(0, int(sr.get("returns") or 0) - _tarde)
        if sr.get("notes_from_search"):
            tail = ""
        elif _a_tiempo:
            tail = "  ⚠️ y NINGUNA se le empujó al cerebro"
        else:
            tail = (f"  · las {_tarde} llegaron DESPUÉS del último turno: no había a quién empujárselas, "
                    f"así que esto NO es un fallo de entrega")
        out.append(f"búsqueda web: {sr['queries']} consulta(s), {sr.get('returns', 0)} respuesta(s), "
                   f"{sr.get('notes_from_search', 0)} nota(s) al cerebro{tail}")
    off = mech.get("offered") or {}
    if off.get("notes"):
        out.append(f"lo que el navegador le OFRECIÓ al cerebro: {off.get('n_offered', 0)} fila(s), "
                   f"{off.get('n_named', 0)} con nombre de verdad "
                   f"(una fila sin nombre, o llamada «169», no es un resultado)")
    q = mech.get("quiescence") or {}
    if q.get("settled") is False:
        out.append(f"⚠️ el motor SEGUÍA trabajando al medir ({q.get('waited_s')}s de espera, "
                   f"{q.get('pending_workers', 0)} worker(s) sin cerrar): lo que falte puede ser "
                   f"«todavía no», no «nunca»")
    return out
