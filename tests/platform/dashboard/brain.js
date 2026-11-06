/* THE BRAIN — one turn of one round through the turn pipeline, as the judge viewer's companion.
   A FIXED picture of the pipeline (zaelar-architecture.md §5i: gate → brief → memory → prompt → router → the main
   stream → reflexes/tools → doors → spec/circuit → task row & Brain Worker → notices → mouth) and, for ONE turn,
   the stations the signal actually crossed lit in the order it crossed them, each with the state it carried.
   The dark stations that SHOULD have fired are the point of the screen: red, with the check that expected them.
   Read from the sandbox's observability DB by the turn's corr_id; the raw flow is a link out, never repainted. */
import { $, esc, clip, api, ms, empty, roundHref, brainHref, flag } from "./lib.js";

export function mount(view, file, idx, turn) {
  view.innerHTML = `<div class="empty">reading the turn's flow…</div>`;
  api(`/api/turn?file=${encodeURIComponent(file)}&idx=${idx}&turn=${turn}`).then(d => render(view, d)).catch(e => { view.innerHTML = empty("unreadable", String(e)); });
  return () => {};
}

function render(view, d) {
  $("crumb").textContent = `${d.scenario || ""} · ${(d.locale || "").toUpperCase()} · turn ${d.turn}${d.n_turns ? ` of ${d.n_turns}` : ""}`;
  const strip = (d.strip || []).map(s => `<a href="${brainHref(d.file, d.idx, s.turn)}" class="${s.turn === d.turn ? "on" : ""}" title="${esc(s.corr_id || "no flow found")}">
      <span>turn ${s.turn}</span><span class="dots">${d.stations.map(st => `<i class="${s.lit.includes(st.id) ? "on" : ""}" title="${esc(st.label)}"></i>`).join("")}</span></a>`).join("");
  const head = `
  <section class="panel"><h2>🧠 ${esc(d.scenario || "")} <span class="sub">${flag(d.locale)} · turn ${d.turn}${d.n_turns ? ` of ${d.n_turns}` : ""}${d.corr_id ? ` · <code>${esc(d.corr_id)}</code> matched by ${esc(d.matched_by)} · ${d.n_events} events over ${ms(d.span_ms)}` : ""}</span>
      <span class="right"><a href="${roundHref(d.file, d.idx)}">← the verdict</a></span></h2>
    <div class="said"><span class="who">heard</span>${esc(d.heard || "")}</div>
    <div class="said" style="margin-top:6px"><span class="who">said</span>${d.said ? esc(d.said) : `<span class="bad">(nothing — a mute turn)</span>`}</div>
    ${strip ? `<div class="strip" style="margin-top:10px">${strip}</div>` : ""}
  </section>`;
  if (!d.readable) {
    view.innerHTML = head + `<section class="panel">${empty("the flow could not be read", d.why || "")}${d.sandbox ? `<div class="muted small">sandbox: <code>${esc(d.sandbox.path)}</code></div>` : ""}</section>`;
    return;
  }
  const order = d.order || [];
  const n = (d.stations || []).filter(s => s.lit).length;
  const dark = (d.stations || []).filter(s => s.expected);
  view.innerHTML = head + `
  <section class="panel"><h2>The turn pipeline <span class="sub">${n} of ${d.stations.length} stations crossed${dark.length ? ` · <b class="bad">${dark.length} expected and dark</b>` : ` · nothing expected is dark`}${d.turn_action ? ` · harness read this turn as <code>${esc(d.turn_action.action || "")}</code>${(d.turn_action.pedido || []).length ? ` asked ${esc(d.turn_action.pedido.join(", "))}` : ""}` : ""}</span></h2>
    <div class="pipeline">${d.stations.map(s => station(s, order)).join("")}</div>
    <div class="links">${d.links.flow_api ? `<a href="${esc(d.links.flow_api)}" target="_blank">the whole flow, raw (the engine's observability API)</a> · <a href="${esc(d.links.engine_url)}" target="_blank">◷ the agent's viewer</a>` : `<span class="faint">the raw flow is in the sandbox's DB — bring the sandbox up to read it through its ◷ viewer</span>`} · <span class="faint">${esc(d.links.db)}</span></div>
  </section>`;
  view.querySelectorAll(".more").forEach(b => b.onclick = () => { const k = b.previousElementSibling; k.querySelectorAll("div[hidden]").forEach(x => x.hidden = false); b.remove(); });
}

function station(s, order) {
  const ord = order.indexOf(s.id);
  const cls = s.lit ? "lit" : s.expected ? "expected" : "";
  const SHOW = 6;
  const kvs = (s.state || []).map((kv, i) => `<div ${i >= SHOW ? "hidden" : ""}><span class="k" title="${esc(kv.k)}">${esc(kv.k)}</span><span class="v">${esc(clip(kv.v == null ? "—" : kv.v, 220))}</span></div>`).join("");
  return `<div class="station ${cls}">
    ${s.lit ? `<span class="ord">${ord + 1}</span>` : ""}
    <div class="nm">${esc(s.label)} <small>${s.lit ? `+${ms(s.first_ms)} · ${s.n} ev` : s.expected ? "dark" : "—"}</small></div>
    <div class="mod">${esc(s.module)}</div>
    ${s.lit ? `<div class="kvs">${kvs}</div>${(s.state || []).length > SHOW ? `<div class="more">+${s.state.length - SHOW} more</div>` : ""}` : `<div class="faint small">${esc(s.hint)}</div>`}
    ${(s.why || []).map(w => `<div class="why">${esc(w)}</div>`).join("")}
  </div>`;
}
