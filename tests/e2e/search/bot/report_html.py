"""tests/e2e/search/bot/report_html.py — informe HTML del test bot de búsqueda para el operador.

Lee `.meshkore/logs/searchbot/progress.json` y escribe un HTML autocontenido en `~/.meshkore/tmp/` (donde el
operador lee los informes). Uso: `./.venv/bin/python -m tests.e2e.search.bot.report_html`.
"""
from __future__ import annotations

import html
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[4]
PROGRESS = REPO / ".meshkore" / "logs" / "searchbot" / "progress.json"
OUT = pathlib.Path.home() / ".meshkore" / "tmp" / "searchbot-report.html"


def build() -> pathlib.Path:
    p = json.loads(PROGRESS.read_text()) if PROGRESS.exists() else {"results": []}
    res = sorted(p.get("results", []), key=lambda r: r.get("i", 0))
    total = len(res)
    passed = sum(1 for r in res if r.get("pass"))
    route_ok = sum(1 for r in res if r.get("route_ok"))
    qflag = [r for r in res if r.get("quality_flag")]
    jflag = [r for r in res if r.get("judge_flag") and r.get("pass")]
    fails = [r for r in res if not r.get("pass")]
    provs = sorted({r.get("source") for r in res if r.get("source")})

    def esc(s): return html.escape(str(s or ""))
    rows = []
    for r in res:
        j = r.get("judge") or {}
        badge = "✅" if r.get("pass") else "❌"
        tags = []
        if r.get("quality_flag"):
            tags.append("<span class='t q'>calidad</span>")
        if r.get("judge_flag") and r.get("pass"):
            tags.append("<span class='t j'>juez?</span>")
        rows.append(
            f"<tr class='{'ok' if r.get('pass') else 'no'}'><td>{r.get('i')}</td><td>{esc(r.get('scope'))}</td>"
            f"<td>{esc(r.get('input'))}</td><td>{esc(r.get('route'))} <small>(esp {esc(r.get('expect'))})</small></td>"
            f"<td>{esc(r.get('source','-'))}</td><td>{esc((r.get('answer') or '')[:180])}</td>"
            f"<td>{badge} {' '.join(tags)}</td></tr>")

    pct = (100 * passed / total) if total else 0
    css = """body{font:15px/1.5 -apple-system,system-ui,sans-serif;margin:0;background:#0e131b;color:#e7eef7}
    .wrap{max-width:1200px;margin:0 auto;padding:28px}h1{font-size:24px;margin:0 0 4px}
    .sub{color:#93a2b4;margin:0 0 20px}.kpis{display:flex;gap:14px;flex-wrap:wrap;margin:18px 0}
    .kpi{background:#151c27;border:1px solid #223;border-radius:12px;padding:14px 18px;min-width:120px}
    .kpi b{font-size:26px;display:block}.kpi span{color:#93a2b4;font-size:13px}
    h2{font-size:18px;margin:26px 0 8px;border-bottom:1px solid #223;padding-bottom:6px}
    table{width:100%;border-collapse:collapse;font-size:13px}td{padding:7px 8px;border-bottom:1px solid #1c2532;vertical-align:top}
    tr.no{background:#2a1416}tr.ok td:first-child{color:#36c08a}small{color:#6b7890}
    .t{font-size:11px;padding:1px 6px;border-radius:6px;margin-left:4px}.t.q{background:#3a2a10;color:#f2b66b}
    .t.j{background:#10263a;color:#5b9dff}.note{background:#151c27;border:1px solid #223;border-radius:10px;padding:14px 16px;color:#c8d3e0}
    li{margin:4px 0}"""
    fail_items = "".join(
        f"<li><b>[{r.get('i')}·{esc(r.get('scope'))}]</b> «{esc(r.get('input'))}» → ruta <code>{esc(r.get('route'))}</code> "
        f"(esperada <code>{esc(r.get('expect'))}</code>)</li>" for r in fails) or "<li>Ninguno.</li>"
    q_items = "".join(
        f"<li><b>[{r.get('i')}]</b> «{esc(r.get('input'))}» → «{esc((r.get('answer') or '')[:140])}»</li>" for r in qflag) or "<li>Ninguno.</li>"

    doc = f"""<!doctype html><html lang=es><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Búsqueda web — informe del test bot</title>
<style>{css}</style></head><body><div class=wrap>
<h1>Test bot de búsqueda web — informe</h1>
<p class=sub>zaelar · V2-022 · routing del FlashBrain + calidad de respuesta · fuente(s): {esc(', '.join(provs) or '—')}</p>
<div class=kpis>
  <div class=kpi><b>{passed}/{total}</b><span>casos que pasan ({pct:.0f}%)</span></div>
  <div class=kpi><b>{route_ok}/{total}</b><span>routing correcto</span></div>
  <div class=kpi><b>{len(qflag)}</b><span>respuestas pobres (calidad)</span></div>
  <div class=kpi><b>{len(jflag)}</b><span>marcadas por el juez</span></div>
</div>
<div class=note><b>Cómo leer esto.</b> «Routing» = si el FlashBrain decidió bien (buscar / no buscar / escalar) — es
lo más importante. «Calidad» marca respuestas evasivas («no encontré…») típicas del buscador GRATIS (DuckDuckGo) en
datos estructurados; se resuelven con un proveedor de respuesta-IA (Perplexity/Tavily). «Juez?» son datos volátiles
donde el juez LLM puede estar desactualizado respecto a la búsqueda en vivo (revisión humana).</div>
<h2>Fallos ({len(fails)})</h2><ul>{fail_items}</ul>
<h2>Respuestas pobres — argumento para el proveedor de respuesta-IA ({len(qflag)})</h2><ul>{q_items}</ul>
<h2>Todos los casos</h2>
<table><tr><td>#</td><td>scope</td><td>input</td><td>ruta</td><td>fuente</td><td>respuesta</td><td>✓</td></tr>
{''.join(rows)}</table>
</div></body></html>"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc, encoding="utf-8")
    return OUT


if __name__ == "__main__":
    print("informe HTML →", build())
