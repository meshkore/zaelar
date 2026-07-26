// BenchmarksPanel — "¿Quieres ver los benchmarks y el por qué usamos unos modelos u otros?" (V2-077, 2026-07-26).
// Réplica VISIBLE al usuario de las decisiones de modelo del sistema — misma filosofía que web/technology: una
// foto curada del contexto interno (config/model_benchmarks.py), no un parser del doc denso. Puramente
// informativo (sin guardar nada); abierta desde el botón al fondo de "Cerebro rápido" en ConfigPanel.
import { h, raw } from "../core/dom.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as api from "../services/api.js?v=2";
import { BRAIN_ICON } from "../lib/icons.js?v=1";

const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const money = v => (v == null ? "—" : `$${Number(v).toFixed(2)}/M`);

function moduleCard(m) {
  const cur = m.current || {};
  const costLine = (cur.cost_in != null || cur.cost_out != null)
    ? `${money(cur.cost_in)} in · ${money(cur.cost_out)} out` : "coste no medido en $/M (uso interno, no FlashBrain)";
  const candidates = m.candidates_2026_07_26 || [];
  const candRows = candidates.map(c => `
    <tr class="${c.verdict ? "bp-cand-rejected" : "bp-cand-open"}">
      <td class="bp-cand-model">${esc(c.model)}</td>
      <td>${esc(typeof c.cost_in === "number" ? money(c.cost_in) : (c.cost_in ?? "—"))} / ${esc(typeof c.cost_out === "number" ? money(c.cost_out) : (c.cost_out ?? "—"))}</td>
      <td>${esc(c.tool_calling || "—")}</td>
      <td>${esc(c.ttft_ms != null ? c.ttft_ms : "—")}</td>
      <td class="bp-cand-status">${esc(c.verdict || c.status || "—")}</td>
    </tr>`).join("");
  return `<section class="cf-panel-sec bp-card">
    <header class="cf-panel-head"><h4>${esc(m.label)}</h4><p>${esc(m.role)}</p></header>
    <div class="cf-group bp-current">
      <div class="cf-row2"><label class="cf-row2-label">Modelo actual</label>
        <div class="cf-row2-ctl bp-right"><span class="bp-model">${esc(cur.model || "—")}</span>
          <span class="cf-hint">${esc(cur.provider || "")}${cur.since ? " · desde " + esc(cur.since) : ""}</span></div></div>
      <div class="cf-row2"><label class="cf-row2-label">Coste</label>
        <div class="cf-row2-ctl bp-right"><span class="bp-model">${esc(costLine)}</span></div></div>
      ${cur.ttft_ms ? `<div class="cf-row2"><label class="cf-row2-label">Latencia (TTFT)</label>
        <div class="cf-row2-ctl bp-right"><span class="bp-model">${esc(cur.ttft_ms)}ms</span></div></div>` : ""}
      <div class="cf-row2"><label class="cf-row2-label">Por qué este</label>
        <div class="cf-row2-ctl bp-right bp-why">${esc(m.why || "—")}</div></div>
      ${m.hallucination_note ? `<div class="cf-row2"><label class="cf-row2-label">Alucinación / fiabilidad</label>
        <div class="cf-row2-ctl bp-right bp-hallu">${esc(m.hallucination_note)}</div></div>` : ""}
    </div>
    ${candidates.length ? `<div class="bp-candtitle">Candidatos evaluados</div>
      <table class="bp-cand-table"><thead><tr><th>modelo</th><th>coste in/out</th><th>tool-calling</th><th>TTFT (ms)</th><th>estado</th></tr></thead>
      <tbody>${candRows}</tbody></table>` : ""}
  </section>`;
}

export function BenchmarksPanel() {
  let bodyEl;
  const close = () => store.setBenchmarksOpen(false);

  async function load() {
    bodyEl.innerHTML = '<p class="cf-loading">Cargando benchmarks…</p>';
    try {
      const data = await api.getBenchmarks();
      const mods = (data.modules || []).map(moduleCard).join("");
      bodyEl.innerHTML = `<div class="cf-scroll"><div class="cf-panel bp-panel">
        <p class="bp-intro">Por qué usamos cada modelo donde lo usamos — coste, latencia y fiabilidad medidos, no
        solo la ficha del proveedor. Fuente detallada: <code>${esc(data.source_doc || "")}</code>
        (actualizado ${esc(data.updated || "")}). Esto es solo informativo — cambiar un modelo de verdad se hace
        en las secciones normales de arriba.</p>
        ${mods || '<p class="cf-loading">Sin datos.</p>'}
      </div></div>`;
    } catch (e) {
      bodyEl.innerHTML = '<p class="cf-loading">No pude cargar /api/config/benchmarks</p>';
    }
  }

  const onKey = e => { if (e.key === "Escape" && store.benchmarksOpen()) close(); };
  window.addEventListener("keydown", onKey);

  const ovl = h("div", { class: () => "cfgfull" + (store.benchmarksOpen() ? " open" : ""), onClick: e => { if (e.target === ovl) close(); } },
    h("div", { class: "cf-shell" },
      h("div", { class: "cf-head" },
        h("h3", {}, raw(BRAIN_ICON), "Benchmarks · por qué estos modelos"),
        h("button", { class: "cf-x", onClick: close }, "cerrar"),
      ),
      h("div", { class: "cf-body", ref: el => (bodyEl = el) }, h("p", { class: "cf-loading" }, "Cargando…")),
    ),
  );

  let wasOpen = false;
  createEffect(() => { const o = store.benchmarksOpen(); if (o && !wasOpen) load(); wasOpen = o; });
  return ovl;
}
