/* THE JUDGE VIEWER — one use-case round read as a verdict with its evidence.
     top     · the hand-off card for a developer: blocker #1, scores, state and why, reproduce, code + machine,
               the sandbox and its ◷ viewer, the settle state
     middle  · the mechanism as a CHECKLIST: each expected signal, measured vs expected, the field that proves it
     below   · the conversation as the judge saw it, turn by turn, with the markers (first mute turn, first unbacked
               claim, delivery lag) and the judge's findings beside the turns they cite
   Everything deeper is a link out (the sandbox's ◷ viewer, the flow API, the report .md/.json). */
import { $, esc, clip, api, ago, when, dur, stateBadge, empty, roundHref, brainHref, fileHref, flag, score } from "./lib.js";

export function mountList(view) {
  view.innerHTML = `<section class="panel"><h2>Rounds <span class="sub" id="rSub"></span></h2><div class="body" id="rBody">loading…</div></section>`;
  api("/api/rounds").then(d => {
    const rows = d.rounds || [];
    $("rSub").textContent = `${rows.length} on disk · newest first · a judged round is one result of a report_*.json; an unjudged one waits in pending/`;
    if (!rows.length) { $("rBody").innerHTML = empty("no round on disk", "python -m tests.use_cases.e2e.agent.run --scenario <id> --sandbox"); return; }
    $("rBody").innerHTML = `<table class="tbl"><thead><tr><th>when</th><th>locale</th><th>scenario</th><th>tier</th><th>state</th><th>overall</th><th>blocker #1</th><th>judge</th></tr></thead><tbody>${
      rows.map(r => `<tr><td><a href="${roundHref(r.file, r.idx)}">${when(r.started_at)}</a><br><span class="faint small">${ago(r.started_at)}</span></td><td>${flag(r.locale)}</td>
        <td><a href="${roundHref(r.file, r.idx)}"><b>${esc(r.scenario)}</b></a>${r.pending ? ` <span class="chip">unjudged</span>` : ""}</td><td>${esc(r.tier ?? "")}</td>
        <td>${stateBadge(r.state)}</td><td>${score(r.overall)}</td><td class="muted">${esc(clip(r.veredicto, 160))}</td><td class="faint small">${esc(r.judge)}</td></tr>`).join("")}</tbody></table>`;
  }).catch(e => { $("rBody").innerHTML = empty("unreadable", String(e)); });
  return () => {};
}

export function mount(view, file, idx) {
  view.innerHTML = `<div class="empty">loading the round…</div>`;
  api(`/api/round?file=${encodeURIComponent(file)}&idx=${idx}`).then(d => render(view, d)).catch(e => { view.innerHTML = empty("unreadable", String(e)); });
  return () => {};
}

function render(view, d) {
  if (!d.readable) { view.innerHTML = empty("no such round", d.why || ""); return; }
  $("crumb").textContent = `${d.scenario} · ${d.locale.toUpperCase()} · ${when(d.started_at)}`;
  const sb = d.sandbox;
  const settled = d.settle || {};
  const code = d.code || {};
  const brain = Object.keys((d.brain || {}).n_by_worker || {}).join(" + ");
  view.innerHTML = `
  <section class="panel">
    <h2>${esc(d.scenario)} <span class="sub">${flag(d.locale)} · tier ${esc(d.tier ?? "?")} · ${esc(d.channel)} · ${when(d.started_at)} (${ago(d.started_at)}) · ${dur((d.finished_at || 0) - (d.started_at || 0))} · ${d.n_turns} turns</span>
      <span class="right"><a href="#/rounds">← all rounds</a></span></h2>
    <div class="handoff">
      <div>
        <div class="blocker"><span class="lbl">${d.pending ? "unjudged — the judge has not scored this round (python -m tests.use_cases.e2e.agent.run --judge-pending)" : "the judge's blocker #1"}</span>${esc(d.blocker || (d.pending ? "" : "— the judge wrote no verdict line"))}</div>
        <div class="scoregrid">
          <div class="cell">${stateBadge(d.state)}<small>state</small></div>
          <div class="cell">${score(d.overall)}<small>overall</small></div>
          ${Object.entries(d.scores || {}).map(([k, v]) => { const c = (d.criteria || {})[k] || {}; return `<div class="cell" title="${esc(c.note || "")}">${score(v)}<small>${esc(k)}${(c.turns || []).length ? ` · t${c.turns.join(",")}` : ""}</small></div>`; }).join("")}
        </div>
        ${d.infra_reason ? `<div class="note media"><span class="g">why INFRA</span>${esc(d.infra_reason)}</div>` : ""}
        ${d.data_limit ? `<div class="note media"><span class="g">capped</span>${esc(typeof d.data_limit === "object" ? (d.data_limit.missing || d.data_limit.kind) : d.data_limit)}</div>` : ""}
        <div style="margin-top:10px"><span class="muted small">reproduce (boots a fresh sandbox on the locale's fixed port):</span><code class="cmd">${esc(d.reproduce)}</code></div>
      </div>
      <dl class="facts">
        <dt>code</dt><dd><code>${esc(code.sha || "?")}</code>${code.n_dirty ? ` <span class="amber">${code.n_dirty} dirty file(s): ${esc((code.dirty || []).slice(0, 3).join(", "))}</span>` : ` <span class="ok">clean tree</span>`}</dd>
        <dt>machine</dt><dd>${esc(((d.machine || {}).gpu_models || []).map(g => `${g.name} (${g.size})`).join(", ") || "—")}</dd>
        <dt>models</dt><dd>driver ${esc(d.drive_model || "?")} · judge ${esc(d.judge || "?")}${brain ? ` · worker ${esc(brain)}` : ""}</dd>
        <dt>settle</dt><dd>${esc(settled.pass)}/${esc(settled.n)} <b>${esc(settled.settled || "UNSETTLED")}</b> on <code>${esc(settled.ledger_sha || "?")}</code>${settled.stale === true ? ` <span class="amber">· stale (HEAD ${esc(settled.head)})</span>` : settled.stale === false ? ` <span class="ok">· current</span>` : ""}<br><span class="faint small">${settled.rounds_n || 0} round(s) in the ledger for this case</span></dd>
        <dt>sandbox</dt><dd>${sb ? `<code>${esc(sb.name)}</code> ${sb.alive ? `<span class="livedot"></span> alive on ${sb.port}` : `kept${sb.has_db ? "" : ", no DB"}`}<br><span class="faint small">${esc(sb.path)}</span><br><span class="faint small">matched by ${esc(sb.matched_by)}</span>` : `<span class="muted">no kept workspace matches this round</span>`}</dd>
        <dt>links</dt><dd>${sb && sb.alive ? `<a href="${esc(sb.engine_url)}" target="_blank">◷ the agent's viewer</a> · <a href="${esc(d.links.flow_api)}" target="_blank">flows API</a> · ` : `<span class="faint">◷ viewer needs the sandbox up · </span>`}${d.links.report_md ? `<a href="${fileHref(d.links.report_md)}" target="_blank">report .md</a> · ` : ""}<a href="${fileHref(d.links.report_json)}" target="_blank">round .json</a> · <a href="${brainHref(d.file, d.idx, 0)}">🧠 the brain, turn by turn</a></dd>
      </dl>
    </div>
  </section>

  <section class="panel"><h2>Mechanism <span class="sub">what REALLY happened, as the harness measured it — one row per expected signal, the field of the round .json that proves it</span></h2>
    ${checks(d)}
  </section>

  <section class="panel"><h2>The conversation as the judge saw it <span class="sub">${d.first_mute != null ? `first mute turn ${d.first_mute} · ` : ""}${d.first_claim != null ? `first unbacked claim turn ${d.first_claim} · ` : ""}${d.lag_turn != null ? `rows arrived before turn ${d.lag_turn} · ` : ""}${d.blind_turns ? `${d.blind_turns} blind turn(s) · ` : ""}turns are numbered from 0 as the judge cites them</span></h2>
    <div class="convo">
      <div>${d.turns.map(t => turn(t, d)).join("")}</div>
      <div class="notes-side">
        ${d.findings_unanchored.length ? `<div class="muted small">findings the judge did not pin to a turn</div>` + d.findings_unanchored.map(note).join("") : ""}
        ${d.improvements.length ? `<div class="muted small" style="margin-top:12px">improvements the judge proposed</div>` + d.improvements.map(i => `<div class="note baja"><span class="g">${esc(i.area)}</span>${esc(i.cambio)}<div class="faint small">${esc(i.porque)}</div></div>`).join("") : ""}
        ${d.watchdog.length ? `<div class="muted small" style="margin-top:12px">the watchdog's opinions in flight (an opinion, not a fact)</div>` + d.watchdog.map(w => `<div class="note media"><span class="g">${esc(w.health)} · ${esc(w.action)}</span>${esc(clip(w.reason, 300))}</div>`).join("") : ""}
      </div>
    </div>
  </section>

  ${d.missing.length ? `<section class="panel"><h2>What this round does not carry <span class="sub">written before the harness emitted it — the screen falls back to matching by time or text</span></h2>
    <ul class="missing">${d.missing.map(m => `<li>${esc(m)}</li>`).join("")}</ul>
  </section>` : ""}`;
}

function checks(d) {
  const rows = d.checks || [];
  const sig = d.signals || {};
  const head = `<div class="muted small" style="margin-bottom:8px">expected signals: ${(sig.expected || []).map(s => `<code class="${(sig.missing || []).includes(s) ? "bad" : "ok"}">${esc(s)}</code>`).join(" ") || "—"} · observed families: ${(sig.observed || []).map(s => `<code>${esc(s)}</code>`).join(" ")}</div>`;
  if (!rows.length) return head + empty("no mechanism report", "the verification could not run — absence proves nothing");
  const MK = { ok: "✓", bad: "✕", info: "i", na: "?" };
  return head + `<div class="checks">
    <span class="h"></span><span class="h">check</span><span class="h">measured</span><span class="h">expected</span><span class="h">proof</span>
    ${rows.map(c => `<span class="mk ${esc(c.status)}">${MK[c.status] || "·"}</span><span><b>${esc(c.label)}</b></span><span>${esc(c.measured)}</span><span class="muted">${esc(c.expected)}</span><span class="where">${esc(c.where)}${c.evidence ? `<br><span class="muted">${esc(clip(c.evidence, 120))}</span>` : ""}</span>`).join("")}
  </div>`;
}

function turn(t, d) {
  const first = (t.who !== "tester") && ((d.first_mute === t.turn && t.markers.some(m => m.kind === "mute")) || (d.first_claim === t.turn && t.markers.some(m => m.kind === "claim")));
  const bad = t.markers.some(m => m.kind === "mute" || m.kind === "claim") || (t.notes || []).some(n => n.gravedad === "alta");
  const mech = t.who === "tester" ? "" : [
    t.action ? `<span>action <code>${esc(t.action)}</code></span>` : "",
    t.asked && t.asked.length ? `<span>asked <code>${esc(t.asked.join(", "))}</code></span>` : "",
    t.widget_ops ? `<span>card ops <code>${esc(t.widget_ops.join(", "))}</code></span>` : "",
    t.open_cards ? `<span>open: ${t.open_cards.length ? esc(t.open_cards.join(", ")) : "none"}</span>` : "",
    `<a class="brainlink" href="${brainHref(d.file, d.idx, t.turn)}">🧠 brain</a>`,
    t.viewer ? `<a class="brainlink" href="${esc(t.viewer)}" target="_blank" title="${esc(t.corr_id)}">◷ this turn</a>` : "",
  ].filter(Boolean).join("");
  return `<div class="tturn ${esc(t.who)} ${bad ? "marked" : ""} ${first ? "first" : ""}">
    <div class="who">${esc(t.who)}<b>${t.who === "tester" ? `turn ${t.turn}` : (t.rel_s != null ? `+${t.rel_s} s` : "")}</b></div>
    <div><div class="tx ${t.text ? "" : "mute"}">${t.text ? esc(t.text) : "(no reply)"}</div>
      ${t.markers.map(m => `<span class="marker ${esc(m.kind)}">${esc(m.text)}</span>`).join("")}
      ${mech ? `<div class="mech">${mech}</div>` : ""}
      ${(t.notes || []).map(note).join("")}
    </div></div>`;
}
function note(f) {
  return `<div class="note ${f.gravedad === "alta" ? "" : f.gravedad === "media" ? "media" : "baja"}"><span class="g">${esc(f.gravedad)} · ${esc(f.turno)}</span>${esc(f.problema)}</div>`;
}
