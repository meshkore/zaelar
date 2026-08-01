"""Turn scenario runs + judge verdicts into improvement reports for zaelar's code team.

Writes two files to tests/runs/agent/:
  · report_<stamp>.md   — human/agent-readable: summary, per-scenario findings, a prioritized list of concrete
                          improvements (this is what you hand to the code agents), and a latency table.
  · report_<stamp>.json — the same, machine-readable.
Independent artifact: built only from the tester's own transcripts/metrics/judgements."""
from __future__ import annotations

import json
from pathlib import Path

_SEV = {"alta": 0, "media": 1, "baja": 2}


def _latency_row(run: dict) -> str:
    m = run.get("latency_ms", {}) or {}
    return f"{m.get('avg','—')}avg / {m.get('max','—')}max ms (n={m.get('n',0)})"


def build(results: list[dict], stamp: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    # consolidate improvements across scenarios, sorted by the severity of the findings in that scenario
    improvements: list[dict] = []
    for r in results:
        v = r.get("verdict", {})
        sev = min((_SEV.get(f.get("gravedad", "baja"), 2) for f in v.get("findings", [])), default=2)
        for imp in v.get("improvements", []):
            improvements.append({**imp, "scenario": r["scenario"], "_sev": sev})
    improvements.sort(key=lambda x: x["_sev"])

    lines = [f"# zaelar — informe de testing de voz ({stamp})", "",
             "Generado por el tester independiente (INI-013). El usuario lo simula un bot; se juzga a ZAELAR por su "
             "comportamiento observable. Entrega este archivo al equipo de código para ir mejorando zaelar.", "",
             "## Resumen por escenario", "",
             "| escenario | canal | overall | latencia | veredicto |", "|---|---|---|---|---|"]
    for r in results:
        v = r.get("verdict", {})
        lines.append(f"| {r['scenario']} | {r.get('channel','')} | {v.get('overall','—')}/5 | "
                     f"{_latency_row(r.get('run',{}))} | {(v.get('veredicto','') or '')[:90]} |")

    lines += ["", "## Mejoras propuestas (priorizadas — para el equipo de código)", ""]
    if improvements:
        for i, imp in enumerate(improvements, 1):
            lines.append(f"{i}. **[{imp['scenario']}] {imp.get('area','?')}** — {imp.get('cambio','')}")
            lines.append(f"   · _por qué_: {imp.get('porque','')}")
    else:
        lines.append("_(sin mejoras propuestas — o el juez no devolvió ninguna)_")

    lines += ["", "## Hallazgos por escenario", ""]
    for r in results:
        v = r.get("verdict", {})
        lines.append(f"### {r['scenario']} ({r.get('channel','')})")
        sc = v.get("scores", {})
        if sc:
            lines.append("scores: " + ", ".join(f"{k} {val}" for k, val in sc.items())
                         + f"  · juez: {v.get('_judge_model','?')}")
        # OBSERVABILITY: what actually fired in the frontend/brain (the judge's source of truth for 'accion')
        tr = r.get("run", {}).get("trace", {}) or {}
        acts = tr.get("frontend_actions", [])
        lines.append(f"acciones de frontend observadas: {', '.join(acts) if acts else '(ninguna)'}")
        if r.get("run", {}).get("dispatch_dead_after_retry"):
            lines.append("⚠️ **silencio total incluso tras reintentar con una sala nueva** — descarta ruido de un "
                         "solo intento; muy probablemente un fallo real de dispatch de LiveKit o de zaelar, no del "
                         "guion del escenario (ver INI-013 §dispatch intermitente).")
        for f in v.get("findings", []):
            lines.append(f"- [{f.get('gravedad','?')}] {f.get('turno','')}: {f.get('problema','')}")
        # short transcript
        for t in r.get("run", {}).get("transcript", [])[:12]:
            who = t["who"]
            lat = f" <{t['latency_ms']}ms>" if t.get("latency_ms") is not None else ""
            lines.append(f"    {who:7} {(t.get('text') or '(timeout)')[:80]}{lat}")
        lines.append("")

    md = out_dir / f"report_{stamp}.md"
    md.write_text("\n".join(lines), encoding="utf-8")
    js = out_dir / f"report_{stamp}.json"
    js.write_text(json.dumps({"stamp": stamp, "results": results, "improvements": improvements},
                             ensure_ascii=False, indent=2), encoding="utf-8")
    return md
