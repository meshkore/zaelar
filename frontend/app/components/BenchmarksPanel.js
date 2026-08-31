// BenchmarksPanel — "Want to see the benchmarks and why we use some models over others?" (V2-077, 2026-07-26).
// User-VISIBLE replica of the system's model decisions — same philosophy as web/technology: a curated
// snapshot of internal context (config/model_benchmarks.py), not a parser for the dense document. Purely
// informational (saves nothing); opened from the button at the bottom of "Fast brain" in ConfigPanel.
import { h, raw } from "../core/dom.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as api from "../services/api.js?v=2";
import { BRAIN_ICON } from "../lib/icons.js?v=1";
import { t } from "../core/i18n.js?v=1";

const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const money = v => (v == null ? "—" : `$${Number(v).toFixed(2)}/M`);

function moduleCard(m) {
  const cur = m.current || {};
  const costLine = (cur.cost_in != null || cur.cost_out != null)
    ? `${money(cur.cost_in)} in · ${money(cur.cost_out)} out` : t("bench.cost_not_measured");
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
      <div class="cf-row2"><label class="cf-row2-label">${t("bench.current_model")}</label>
        <div class="cf-row2-ctl bp-right"><span class="bp-model">${esc(cur.model || "—")}</span>
          <span class="cf-hint">${esc(cur.provider || "")}${cur.since ? " · " + t("bench.since", { value: esc(cur.since) }) : ""}</span></div></div>
      <div class="cf-row2"><label class="cf-row2-label">${t("bench.cost")}</label>
        <div class="cf-row2-ctl bp-right"><span class="bp-model">${esc(costLine)}</span></div></div>
      ${cur.ttft_ms ? `<div class="cf-row2"><label class="cf-row2-label">${t("bench.latency_ttft")}</label>
        <div class="cf-row2-ctl bp-right"><span class="bp-model">${esc(cur.ttft_ms)}ms</span></div></div>` : ""}
      <div class="cf-row2"><label class="cf-row2-label">${t("bench.why_this")}</label>
        <div class="cf-row2-ctl bp-right bp-why">${esc(m.why || "—")}</div></div>
      ${m.hallucination_note ? `<div class="cf-row2"><label class="cf-row2-label">${t("bench.hallucination")}</label>
        <div class="cf-row2-ctl bp-right bp-hallu">${esc(m.hallucination_note)}</div></div>` : ""}
    </div>
    ${candidates.length ? `<div class="bp-candtitle">${t("bench.candidates_evaluated")}</div>
      <table class="bp-cand-table"><thead><tr><th>${t("bench.col_model")}</th><th>${t("bench.col_cost")}</th><th>${t("bench.col_tool_calling")}</th><th>${t("bench.col_ttft")}</th><th>${t("bench.col_status")}</th></tr></thead>
      <tbody>${candRows}</tbody></table>` : ""}
  </section>`;
}

export function BenchmarksPanel() {
  let bodyEl;
  const close = () => store.setBenchmarksOpen(false);

  async function load() {
    bodyEl.innerHTML = `<p class="cf-loading">${t("bench.loading")}</p>`;
    try {
      const data = await api.getBenchmarks();
      const mods = (data.modules || []).map(moduleCard).join("");
      bodyEl.innerHTML = `<div class="cf-scroll"><div class="cf-panel bp-panel">
        <p class="bp-intro">${t("bench.intro", { source: esc(data.source_doc || ""), updated: esc(data.updated || "") })}</p>
        ${mods || `<p class="cf-loading">${t("bench.no_data")}</p>`}
      </div></div>`;
    } catch (e) {
      bodyEl.innerHTML = `<p class="cf-loading">${t("bench.load_error")}</p>`;
    }
  }

  const onKey = e => { if (e.key === "Escape" && store.benchmarksOpen()) close(); };
  window.addEventListener("keydown", onKey);

  const ovl = h("div", { class: () => "cfgfull" + (store.benchmarksOpen() ? " open" : ""), onClick: e => { if (e.target === ovl) close(); } },
    h("div", { class: "cf-shell" },
      h("div", { class: "cf-head" },
        h("h3", {}, raw(BRAIN_ICON), () => t("bench.header")),
        h("button", { class: "cf-x", onClick: close }, () => t("bench.close")),
      ),
      h("div", { class: "cf-body", ref: el => (bodyEl = el) }, h("p", { class: "cf-loading" }, () => t("bench.loading_short"))),
    ),
  );

  let wasOpen = false;
  createEffect(() => { const o = store.benchmarksOpen(); if (o && !wasOpen) load(); wasOpen = o; });
  return ovl;
}
