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
            lines.append(f"hoja de resultados: {sh.get('n_named', 0)} candidato(s) con nombre "
                         f"de {sh.get('n_items', 0)} fila(s) · {sh.get('n_sources', 0)} fuente(s)"
                         + (f" · {', '.join(sh.get('titles') or [])}" if sh.get("titles") else ""))
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
