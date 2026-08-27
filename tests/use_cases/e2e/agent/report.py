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
        lines.append(f"informe de mecanismo: familias observadas = {mech.get('families_observed', [])}, "
                     f"esperadas = {mech.get('expected_signals', [])}, "
                     f"faltantes = {mech.get('missing_signals', []) or '(ninguna)'}")
        if mech.get("navegador_task_id"):
            nt = mech.get("navegador_task", {})
            lines.append(f"tarea de navegador {mech['navegador_task_id']}: status={nt.get('status','?')}, "
                         f"awaiting_login={nt.get('awaiting_login', False)}, "
                         f"resultados={len((nt.get('results') or {}).get('items', []) or [])}")
        # La HOJA, aparte de la tarjeta y SIEMPRE — es la superficie que el operador mira, y con V2-257 pasa a
        # ser la única que guarda hallazgos. «no la miré» no puede leerse igual que «estaba vacía».
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
            # CADA CAJA POR SEPARADO cuando hay más de una: el total no dice si ESTE encargo fue servido —
            # la caja de al lado puede llevar lo suyo. Es la línea que separa «no entregó» de «entregó en
            # su sitio y el lector miraba en otro».
            _pb = sh.get("per_box") or []
            if len(_pb) > 1:
                lines.append("   por encargo: " + " · ".join(
                    f"{b.get('id')}: {b.get('n_items', 0)} fila(s) «{b.get('title') or ''}»" for b in _pb))
        # UNA CAJA POR ENCARGO. Solo se imprime si hubo alguna apertura: en un caso de un solo encargo no
        # dice nada que no diga ya la línea de arriba, y en uno de dos es la línea que decide el veredicto.
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
        # LOS NÚMEROS DEL MECANISMO, en el informe que se LEE y no solo en el JSON. Hasta 2026-08-21 cada
        # uno de éstos se sacaba a mano con un script suelto y se pegaba en un mensaje: servía mientras
        # hubiera alguien delante haciéndolo, y no sobrevivía a un relevo. El agente que arregla abre este
        # fichero, así que aquí es donde tienen que estar.
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
    """Las cifras que deciden a QUIÉN pertenece un fallo, en una línea cada una y solo si hay algo que decir.

    Cada una nació de un defecto que este arnés atribuyó mal antes de tenerla: `worker_health` porque
    «4 lanzados, 0 ok» se leía como cuatro fallos cuando tres seguían trabajando; `worker_deaths` porque la
    causa de una familia entera de casos estaba en cruzar el almacén con el log y nadie la veía;
    `search_returns` porque la búsqueda contestaba bien y no llegaba a nadie; `quiescence` porque leer
    demasiado pronto convierte «no ha terminado» en «ha fallado».
    """
    out: list[str] = []
    # V2-362 — EL RELOJ, EN EL INFORME. `sheet_timing` se calcula desde V2-300 y se afinó en V2-355, y no
    # se imprimía en ninguna parte: el juez lo recibe en el JSON, pero quien lee el informe —un humano o el
    # agente que va a arreglar el caso— no podía ver el número. Una medida sin lector es una decisión sin
    # llamante: existe y no cambia nada.
    #
    # Y es EL número de la queja del operador («una búsqueda se hace en un minuto, dos o tres máximo»):
    # cuánto tarda el encargo en poner su primera fila delante. Se dice CON el reloj que se usó, porque el
    # flojo («primera escritura» del worker, que puede ser su plan) y el estricto (el intake del navegador,
    # que son candidatos de verdad) no miden lo mismo — y confundirlos es lo que produjo los 130,8 s de
    # «retención» inventados que V2-355 cortó.
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
    dup = mech.get("duplicate_errands") or {}
    # Una CONTINUACIÓN se cuenta, con su motivo, y NO como un fallo de dedup: el coste en tokens es real y
    # tiene que verse, pero llamarlo duplicado manda a mirar un mecanismo que se portó bien (V2-238/V2-117).
    for c in (dup.get("continuations") or [])[:3]:
        out.append(f"· un worker MÁS por continuación del mismo encargo — {c.get('why')}: paga tokens dos "
                   f"veces, pero NO es un duplicado ni un fallo del dedup")
    for g in (dup.get("groups") or [])[:3]:
        _bar, _met = g.get("engine_bar"), g.get("engine_metric") or "contención"
        _bar_txt = f"{_met} del motor {g.get('max_sim')} ≥ {_bar}" if _bar else "sin poder leer la vara del motor"
        _how = (f"el dedup NO disparó ({_bar_txt})" if g.get("over_engine_bar")
                else f"reformulado — el motor lo ve a {g.get('max_sim')}, por debajo de su {_bar}")
        out.append(f"⚠️ **{g.get('n')} workers para UN encargo** · contención {g.get('min_sim')}–"
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
        tail = "" if sr.get("notes_from_search") else "  ⚠️ y NINGUNA se le empujó al cerebro"
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
