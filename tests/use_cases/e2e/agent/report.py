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
