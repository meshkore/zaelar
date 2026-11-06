/* HOME — a dashboard, useful and to the point. Four questions, four panels:
     · who is testing RIGHT NOW (every agent, its set, how far, the case in flight, one click into its run)
     · the sandboxes (the use-case workspaces and the lab: locale, port, alive or kept, age, size, their round)
     · the LAST RESULT per set (unit sweep, benches, use cases ES and US: when, how long, counts, trend, reds named)
     · the scoreboard folded per tier × locale, with the stale rows
   Nothing here launches anything; everything deeper is a link. */
import { $, esc, clip, api, ago, when, dur, bytes, stateBadge, verdictBadge, trend, bar, empty, roundHref, runHref, fileHref, flag, score } from "./lib.js";

let timer = null;

export function mount(view) {
  view.innerHTML = `
    <section class="panel" id="hRunning"><h2>Running now <span class="sub" id="hRunningSub"></span></h2><div class="body">…</div></section>
    <section class="grid4" id="hResults"></section>
    <section class="panel" id="hBoard"><h2>Scoreboard <span class="sub" id="hBoardSub"></span></h2><div class="body">…</div></section>
    <section class="panel" id="hSandboxes"><h2>Sandboxes <span class="sub" id="hSandSub"></span></h2><div class="body">…</div></section>`;
  const tick = async () => { await Promise.allSettled([running(), results(), sandboxes()]); };
  tick();
  timer = setInterval(running, 4000);
  const slow = setInterval(() => { results(); sandboxes(); }, 20000);
  return () => { clearInterval(timer); clearInterval(slow); };
}

async function running() {
  let data;
  try { data = await api("/api/running"); } catch { return; }
  const rows = data.running || [];
  $("hRunningSub").textContent = rows.length ? `${rows.length} agent${rows.length === 1 ? "" : "s"}` : "";
  const host = $("hRunning").querySelector(".body");
  if (!rows.length) {
    host.innerHTML = empty("Nobody is testing right now", "An agent's run appears here the moment it starts: python -m tests run <suite> --no-open");
    return;
  }
  host.innerHTML = `<div class="runcards">` + rows.map(r => {
    const pct = r.total ? Math.min(100, 100 * r.done / r.total) : 0;
    const cur = r.current || {};
    const where = cur.test_id ? `<b>${esc(clip(cur.label || cur.test_id, 90))}</b>${cur.step ? ` <span class="muted">— ${esc(cur.step)}</span>` : ""}${
      cur.turn ? ` <span class="muted">· turn ${cur.turn}${cur.turn_budget ? "/" + cur.turn_budget : ""}</span>` : ""}`
      : `<span class="muted">${r.total ? "between cases" : "collecting…"}</span>`;
    return `<a class="runcard" href="${runHref(r.run_id)}">
      <div class="rc-head"><span class="livedot"></span><b>${esc(r.actor)}</b>
        <span class="chip">${esc(r.suite)}</span><span class="muted">${esc(clip(r.target, 60))}</span>
        <span class="right muted">started ${ago(r.started_at)} · ${dur(r.elapsed_s)}</span></div>
      <div class="rc-prog"><div class="stack"><i class="PASS" style="width:${(r.total ? 100 * r.passed / r.total : 0).toFixed(1)}%"></i><i class="FAIL" style="width:${(r.total ? 100 * r.failed / r.total : 0).toFixed(1)}%"></i><i class="NONE" style="width:${(r.total ? 100 * r.skipped / r.total : 0).toFixed(1)}%"></i></div>
        <span class="nums"><b>${r.done}</b> / ${r.total || "?"} <span class="muted">· ${pct.toFixed(0)} %</span>
          <span class="ok">${r.passed} ✓</span> <span class="${r.failed ? "bad" : "muted"}">${r.failed} ✕</span></span></div>
      <div class="rc-now">${where}</div>
      ${r.reds && r.reds.length ? `<div class="rc-reds">reds: ${r.reds.map(x => `<code>${esc(clip(x, 70))}</code>`).join(" ")}</div>` : ""}
    </a>`;
  }).join("") + `</div>`;
}

async function results() {
  let d;
  try { d = await api("/api/results"); } catch (e) { $("hResults").innerHTML = empty("results unreadable", String(e)); return; }
  $("hResults").innerHTML = unitCard(d.unit) + benchCard(d.benches) + ucCard("es", d.use_cases.es) + ucCard("us", d.use_cases.us);
  board(d.scoreboard);
}

function unitCard(u) {
  const l = u.last;
  if (!l) return card("Unit sweep", "", empty("no sweep on disk", "tests/watchdog.py writes tests/runs/watchdog-*.json"));
  const c = l.totals && Object.keys(l.totals).length ? l.totals : l.counts;
  const tr = u.trend ? trend(u.trend.reds, { invert: true, unit: " reds" }) : trend(null);
  return card("Unit sweep", `${when(l.at)} · ${ago(l.at)}`, `
    <div class="kpi">${verdictBadge(l.verdict)} <b>${esc(c.passed || 0)}</b> passed · <b class="${c.failed ? "bad" : ""}">${esc(c.failed || 0)}</b> failed${
      c.error ? ` · ${c.error} error` : ""}${c.skipped ? ` · ${c.skipped} skipped` : ""}</div>
    <div class="muted">${dur(l.seconds)} · ${l.targets} target${l.targets === 1 ? "" : "s"} · ${tr}</div>
    ${bar([{ n: c.passed || 0, cls: "PASS" }, { n: c.failed || 0, cls: "FAIL" }, { n: c.skipped || 0, cls: "NONE" }], (c.passed || 0) + (c.failed || 0) + (c.skipped || 0))}
    ${l.hung.length ? `<div class="reds"><b>hung:</b> ${l.hung.map(h => `<code>${esc(h)}</code>`).join(" ")}</div>` : ""}
    ${l.reds.length ? `<div class="reds"><b>${l.n_reds} red${l.n_reds === 1 ? "" : "s"}:</b> ${l.reds.slice(0, 6).map(x => `<code title="${esc(x)}">${esc(shortNode(x))}</code>`).join(" ")}${l.n_reds > 6 ? ` <span class="muted">+${l.n_reds - 6}</span>` : ""}</div>` : `<div class="ok">no reds</div>`}
    <div class="links"><a href="${fileHref(l.file)}" target="_blank">sweep json</a> · <a href="#/sets/unit">by folder →</a></div>`);
}
const shortNode = x => { const [f, t] = String(x).split("::"); return (f.split("/").pop() || f) + (t ? "::" + t : ""); };

function benchCard(bs) {
  const rows = bs.map(b => {
    const l = b.last;
    if (!l) return `<tr class="dim"><td>${esc(b.module)}</td><td colspan="3" class="muted">no run file on disk · by request</td></tr>`;
    const head = l.headline_label ? `<b>${esc(l.headline)}</b> <span class="muted">${esc(l.headline_label)}</span>` : "";
    const tr = b.trend ? trend(b.trend.headline) : "";
    return `<tr><td>${esc(b.module)}</td><td>${when(l.at_epoch)}</td><td>${head}</td><td class="muted">${tr}</td></tr>`;
  }).join("");
  return card("Benches", `${bs.filter(b => b.last).length} of ${bs.length} with a run on disk`,
    `<table class="mini"><tbody>${rows}</tbody></table><div class="links"><a href="#/sets/benches">the table →</a></div>`);
}

function ucCard(loc, u) {
  const title = `Use cases ${flag(loc)}`;
  if (!u || !u.n) return card(title, "", empty("no round on disk", "python -m tests.use_cases.e2e.agent.run --sandbox …"));
  const st = u.states || {};
  const total = u.n;
  const tr = u.trend ? trend(u.trend.pass, { unit: " PASS" }) : (u.source === "ledger" ? `<span class="trend flat">from the ledger</span>` : trend(null));
  return card(title, `${when(u.at)} · ${ago(u.at)}`, `
    <div class="kpi">${["PASS", "FAIL", "INFRA", "CAPPED"].map(k => st[k] ? `${stateBadge(k)} <b>${st[k]}</b>` : "").filter(Boolean).join(" ")} <span class="muted">of ${total}</span></div>
    <div class="muted">${dur(u.seconds)} · ${tr}</div>
    ${bar(["PASS", "FAIL", "INFRA", "CAPPED"].map(k => ({ n: st[k] || 0, cls: k })), total)}
    ${u.reds && u.reds.length ? `<div class="reds"><b>reds:</b> ${u.reds.map(r => r.file ? `<a href="${roundHref(r.file, r.idx)}" title="${esc(r.veredicto)}">${esc(r.scenario)} ${r.overall != null ? r.overall + "/5" : ""}</a>` : `<span title="${esc(r.veredicto)}">${esc(r.scenario)} ${r.overall != null ? r.overall + "/5" : ""}</span>`).join(" · ")}</div>` : `<div class="ok">no reds</div>`}
    ${u.note ? `<div class="muted small">${esc(u.note)}</div>` : ""}
    <div class="links">${u.report_md ? `<a href="${fileHref(u.report_md)}" target="_blank">report .md</a> · ` : ""}<a href="#/sets/usecases">the catalog →</a> · <a href="#/rounds">all rounds →</a></div>`);
}

function card(title, sub, body) {
  return `<section class="panel"><h2>${esc(title)} <span class="sub">${sub}</span></h2><div class="body">${body}</div></section>`;
}

function board(sb) {
  const host = $("hBoard").querySelector(".body");
  if (!sb || !sb.n) { host.innerHTML = empty("no scoreboard", "tests/use_cases/status.json is written by every use-case round"); return; }
  $("hBoardSub").innerHTML = `${sb.n} rows · updated ${esc(sb.updated || "—")} · HEAD ${esc(sb.head)}${sb.stale_ready ? ` · <b class="${sb.n_stale ? "amber" : "ok"}">${sb.n_stale} stale</b>` : ` · <span class="muted">measuring staleness…</span>`}`;
  const cells = sb.cells || [];
  const tiers = [...new Set(cells.map(c => c.tier))].sort((a, b) => a - b);
  const cell = (t, loc) => cells.find(c => c.tier === t && c.locale === loc);
  const td = c => c ? `<td>${bar(["PASS", "FAIL", "INFRA", "CAPPED"].map(k => ({ n: c[k], cls: k })), c.total)}
      <span class="nums"><span class="ok">${c.PASS}</span>/<span class="bad">${c.FAIL}</span>/<span class="amber">${c.INFRA}</span>/<span class="blue">${c.CAPPED}</span> <span class="muted">of ${c.total}${sb.stale_ready && c.stale ? ` · ${c.stale} stale` : ""}</span></span></td>` : `<td class="muted">—</td>`;
  host.innerHTML = `<table class="board"><thead><tr><th>tier</th><th>${flag("es")}</th><th>${flag("us")}</th></tr></thead><tbody>${
    tiers.map(t => `<tr><td class="tier">tier ${t}</td>${td(cell(t, "es"))}${td(cell(t, "us"))}</tr>`).join("")}</tbody></table>
    <div class="legend">${stateBadge("PASS")} ≥ 4/5 · ${stateBadge("FAIL")} · ${stateBadge("INFRA")} not measured · ${stateBadge("CAPPED")} needs the user's own credentials · <b>stale</b>: product code moved since that row was measured</div>
    ${sb.stale_ready && sb.stale.length ? `<details class="stale"><summary>${sb.n_stale} stale row${sb.n_stale === 1 ? "" : "s"} — oldest first</summary><div class="chips">${
      sb.stale.slice(0, 60).map(r => `<span class="chip st-${esc(r.state)}" title="${esc(r.last_run)} · ${esc(r.sha)}">${esc(r.id)}</span>`).join("")}${sb.stale.length > 60 ? `<span class="muted">+${sb.stale.length - 60}</span>` : ""}</div></details>` : ""}`;
}

async function sandboxes() {
  let d;
  try { d = await api("/api/sandboxes"); } catch (e) { return; }
  const rows = d.sandboxes || [];
  let roundsByFile = {};
  try { const rr = await api("/api/rounds"); roundsByFile = rr.rounds || []; } catch { roundsByFile = []; }
  $("hSandSub").textContent = rows.length ? `${rows.length} kept · ${rows.filter(r => r.alive).length} alive` : "";
  const host = $("hSandboxes").querySelector(".body");
  if (!rows.length) { host.innerHTML = empty("no sandbox kept", "a use-case round keeps its workspace under tests/runs/use_cases/sandbox/<stamp>-<lang>"); return; }
  const roundOf = s => {
    /* the round(s) this workspace made: same locale, first turn after the boot, before the next boot of that locale */
    const next = rows.filter(x => x.locale === s.locale && x.kind === s.kind && x.stamp > s.stamp).map(x => x.stamp).sort((a, b) => a - b)[0] || (s.stamp + 6 * 3600);
    return roundsByFile.filter(r => r.locale === s.locale && r.started_at >= s.stamp - 2 && r.started_at < next);
  };
  host.innerHTML = `<table class="tbl"><thead><tr><th>workspace</th><th>locale</th><th>port</th><th>state</th><th>age</th><th>size</th><th>the round that made it</th><th>links</th></tr></thead><tbody>${
    rows.map(s => {
      const rs = roundOf(s);
      return `<tr class="${s.alive ? "alive" : ""}">
      <td><code>${esc(s.name)}</code>${s.kind === "lab" ? ` <span class="chip">lab</span>` : ""}</td>
      <td>${flag(s.locale)}</td><td>${s.port || "—"}</td>
      <td>${s.alive ? `<span class="livedot"></span> alive${s.engine && s.engine.version ? ` <span class="muted">${esc(s.engine.version)}</span>` : ""}` : s.has_db ? `kept` : `<span class="muted">config only — never booted</span>`}</td>
      <td title="${when(s.stamp)}">${ago(s.stamp)}</td><td>${s.size == null ? `<span class="faint">measuring…</span>` : bytes(s.size)}</td>
      <td>${rs.length ? rs.slice(0, 3).map(r => `<a href="${roundHref(r.file, r.idx)}">${esc(r.scenario)}</a> ${stateBadge(r.state)}${r.overall != null ? ` <small>${r.overall}/5</small>` : ""}`).join("<br>") + (rs.length > 3 ? `<br><span class="muted">+${rs.length - 3} more</span>` : "") : `<span class="muted">no round file matches (pruned, or never judged)</span>`}</td>
      <td>${s.alive ? `<a href="${esc(s.engine.url)}" target="_blank">◷ engine</a> · <a href="${esc(s.engine.url)}/api/observability/flows?limit=30" target="_blank">flows</a>` : `<span class="muted">◷ needs the engine up</span>`}${rs[0] && rs[0].report_md ? ` · <a href="${fileHref(rs[0].report_md)}" target="_blank">report</a>` : ""}</td></tr>`;
    }).join("")}</tbody></table>`;
}
