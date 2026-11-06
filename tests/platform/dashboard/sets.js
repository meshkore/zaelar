/* TEST SETS — the three layers as sets, each with its last result.
     · unit       — tests/<area> → folders → files; the last sweep each folder got (the watchdog runs folders)
     · benches    — the module benches of tests/README.md §Module benches, with their last run file
     · use cases  — the catalog by language → theme → tier, with the verdict per case (ledger + newest round)
   The spine language → family → theme is kept: the language selects a SET, never a subset. */
import { $, esc, clip, api, ago, when, dur, stateBadge, verdictBadge, trend, empty, roundHref, fileHref, flag, score } from "./lib.js";

const LOC_KEY = "zaelar.observatory.locale";

export function mount(view, which) {
  view.innerHTML = `
    <div class="toolbar">
      <nav class="subnav">
        <a href="#/sets/unit" class="${which === "unit" ? "on" : ""}">Unit · deterministic</a>
        <a href="#/sets/benches" class="${which === "benches" ? "on" : ""}">Module benches</a>
        <a href="#/sets/usecases" class="${which === "usecases" ? "on" : ""}">Use cases</a>
      </nav>
      <span id="setsTools" class="toolbar"></span>
    </div>
    <div id="setsBody"><div class="empty">loading…</div></div>`;
  if (which === "unit") unit();
  else if (which === "benches") benches();
  else usecases();
  return () => {};
}

/* ─── unit ──────────────────────────────────────────────────────────────── */
async function unit() {
  let d;
  try { d = await api("/api/sets/unit"); } catch (e) { $("setsBody").innerHTML = empty("unreadable", String(e)); return; }
  const l = d.last_sweep;
  $("setsTools").innerHTML = l ? `<span class="muted">last sweep ${when(l.at)} (${ago(l.at)}) · ${verdictBadge(l.verdict)} · ${dur(l.seconds)} · ${l.targets} target${l.targets === 1 ? "" : "s"} · <a href="${fileHref(l.file)}" target="_blank">json</a></span>`
    : `<span class="muted">no sweep on disk</span>`;
  const areas = d.areas || [];
  $("setsBody").innerHTML = `<div class="muted small" style="margin-bottom:8px">A folder is the unit the watchdog sweeps and reports. «never swept» = no sweep in the last ${d.sweeps_read} report${d.sweeps_read === 1 ? "" : "s"} covered it; a scope of «N file(s)» means an <code>--impacted</code> sweep touched only those.</div>` +
    areas.map(a => `<details class="area" ${a.reds || a.hung ? "open" : ""}>
      <summary><span>${esc(a.label)} <span class="n">tests/${esc(a.id)}</span></span>
        <span class="n">${a.folders.length} folder${a.folders.length === 1 ? "" : "s"} · ${a.files} files</span>
        <span class="${a.reds ? "bad" : "ok"}">${a.reds ? `${a.reds} red file${a.reds === 1 ? "" : "s"}` : "no reds"}</span>
        <span class="${a.hung ? "amber" : "faint"}">${a.hung ? `${a.hung} hung` : ""}</span>
        <span class="faint">${a.never_swept ? `${a.never_swept} never swept` : ""}</span></summary>
      ${a.folders.map(f => {
        const sw = f.sweep;
        const c = (sw && sw.counts) || {};
        return `<div class="folder ${f.red_files.length ? "red" : ""} ${f.hung ? "hung" : ""}">
          <span><code>${esc(f.folder)}</code>${f.exists ? "" : ` <span class="bad">missing on disk</span>`}</span>
          <span class="muted">${f.files} f</span>
          <span>${sw ? verdictBadge(sw.verdict) : `<span class="never">never swept</span>`}</span>
          <span class="muted small">${sw ? `${ago(sw.at)} · ${dur(sw.seconds)} · ${esc(sw.scope)}` : ""}</span>
          <span class="small">${sw ? `<span class="ok">${c.passed || 0} ✓</span> <span class="${c.failed ? "bad" : "faint"}">${c.failed || 0} ✕</span>` : ""}${
            f.hung ? ` <span class="amber">hung at ${esc(clip(sw.hung_at, 80))}</span>` : ""}${
            f.red_files.length ? `<div class="reds">${f.red_files.map(x => `<code>${esc(x.split("/").pop())}</code>`).join(" ")}</div>` : ""}</span>
        </div>`; }).join("")}
    </details>`).join("");
}

/* ─── benches ───────────────────────────────────────────────────────────── */
async function benches() {
  let d;
  try { d = await api("/api/sets/benches"); } catch (e) { $("setsBody").innerHTML = empty("unreadable", String(e)); return; }
  const rows = d.benches || [];
  $("setsTools").innerHTML = `<span class="muted">one module against its real dependency, fixed data, numbers — by request, after a change to that module</span>`;
  $("setsBody").innerHTML = `<section class="panel"><table class="tbl"><thead><tr><th>module</th><th>bench</th><th>what it measures</th><th>last run</th><th>numbers</th><th>trend</th></tr></thead><tbody>${
    rows.map(b => {
      const l = b.last;
      return `<tr class="${l ? "" : "dim"}"><td><b>${esc(b.module)}</b></td><td><code>${esc(b.command)}</code></td><td class="muted">${esc(b.measures)}</td>
        <td>${l ? `${when(l.at_epoch)}<br><span class="muted small">${ago(l.at_epoch)} · <a href="${fileHref(l.file)}" target="_blank">file</a> · ${b.runs_on_disk} on disk</span>` : `<span class="muted">no run file on disk</span>`}</td>
        <td>${l ? numbers(b.kind, l) : ""}</td><td>${b.trend ? trend(b.trend.headline) : (l ? trend(null) : "")}</td></tr>`;
    }).join("")}</tbody></table></section>`;
}
function numbers(kind, l) {
  if (kind === "search") return `<b>${esc(l.headline)}</b> <span class="muted">${esc(l.headline_label)}</span><div class="small muted">${Object.entries(l.providers || {}).map(([k, v]) => `${esc(k)} <b>${esc(v.score)}</b> · ${esc(v.lat_s)} s${v.errors ? ` · ${v.errors} err` : ""}`).join(" &nbsp;·&nbsp; ")}<br>${l.cases} cases · judge ${esc(l.judge || "—")} · ${esc(l.mode || "")}</div>`;
  if (kind === "scrape") return `<b>${esc(l.met)}</b> / ${esc(l.sites)} <span class="muted">sites over their floor</span>${l.failed && l.failed.length ? `<div class="reds"><b>under:</b> ${l.failed.map(x => `<code>${esc(x)}</code>`).join(" ")}</div>` : ""}`;
  if (kind === "jev") return `<b>${esc(l.hit)}</b> / ${esc(l.phrases)} <span class="muted">as wanted · ${esc(l.question)} · ${esc(l.ms_avg)} ms avg</span>${l.misses && l.misses.length ? `<div class="reds"><b>missed:</b> ${l.misses.map(x => `<code>${esc(x)}</code>`).join(" ")}</div>` : ""}`;
  return l.headline != null ? `<b>${esc(l.headline)}</b> <span class="muted">${esc(l.headline_label || "")}</span>` : "";
}

/* ─── use cases ─────────────────────────────────────────────────────────── */
const UC = { locale: localStorage.getItem(LOC_KEY) || "es", state: "", tier: "", q: "", data: null };
async function usecases() {
  try { UC.data = await api("/api/sets/usecases"); } catch (e) { $("setsBody").innerHTML = empty("unreadable", String(e)); return; }
  renderUcTools();
  renderUc();
}
function renderUcTools() {
  const all = UC.data.groups.flatMap(g => g.cases);
  const n = loc => all.filter(c => c.locale === loc).length;
  $("setsTools").innerHTML = `
    <div class="langsel" id="langsel"><button data-loc="es" class="${UC.locale === "es" ? "on" : ""}">${flag("es")} <span class="muted">${n("es")}</span></button><button data-loc="us" class="${UC.locale === "us" ? "on" : ""}">${flag("us")} <span class="muted">${n("us")}</span></button></div>
    <select id="ucState"><option value="">any state</option>${["PASS", "FAIL", "INFRA", "CAPPED", "—"].map(s => `<option ${UC.state === s ? "selected" : ""}>${s}</option>`).join("")}</select>
    <select id="ucTier"><option value="">any tier</option>${[...new Set(all.map(c => c.tier))].sort((a, b) => a - b).map(t => `<option value="${t}" ${String(UC.tier) === String(t) ? "selected" : ""}>tier ${t}</option>`).join("")}</select>
    <input class="filter" id="ucQ" placeholder="filter by id, title, theme…" value="${esc(UC.q)}" style="max-width:280px">
    <span class="counthint" id="ucCount"></span>`;
  document.querySelectorAll("#langsel button").forEach(b => b.onclick = () => { UC.locale = b.dataset.loc; localStorage.setItem(LOC_KEY, UC.locale); renderUcTools(); renderUc(); });
  $("ucState").onchange = e => { UC.state = e.target.value; renderUc(); };
  $("ucTier").onchange = e => { UC.tier = e.target.value; renderUc(); };
  $("ucQ").oninput = e => { UC.q = e.target.value; renderUc(); };
}
function renderUc() {
  const q = UC.q.toLowerCase();
  const keep = c => c.locale === UC.locale
    && (!UC.state || (UC.state === "—" ? !c.verdict : (c.verdict || {}).state === UC.state))
    && (!UC.tier || String(c.tier) === String(UC.tier))
    && (!q || (c.id + " " + c.title + " " + c.theme + " " + c.utterance).toLowerCase().includes(q));
  const groups = UC.data.groups.map(g => ({ ...g, cases: g.cases.filter(keep) }));
  const total = groups.reduce((a, g) => a + g.cases.length, 0);
  const all = UC.data.groups.flatMap(g => g.cases).filter(c => c.locale === UC.locale);
  $("ucCount").textContent = `${total} of ${all.length} in ${UC.locale.toUpperCase()}`;
  const tally = {};
  for (const c of all) { const s = (c.verdict || {}).state || "—"; tally[s] = (tally[s] || 0) + 1; }
  const head = `<div class="muted small" style="margin-bottom:8px">${Object.entries(tally).map(([s, n]) => `${stateBadge(s)} ${n}`).join(" &nbsp; ")} &nbsp;·&nbsp; «—» = never measured · <span class="staledot"></span> stale: product code moved since the row was measured · k/k = settled rounds on the latest code</div>`;
  if (!total) { $("setsBody").innerHTML = head + empty(`No case in ${UC.locale.toUpperCase()} matches`, all.length ? "widen the filter" : "this set does not exist yet — not filtered, absent"); return; }
  $("setsBody").innerHTML = head + groups.filter(g => g.cases.length).map(g => `<details class="theme" open>
    <summary><span>${esc(g.label)}</span><span class="hint">${esc(g.hint)}</span><span class="muted small">${g.cases.length}</span></summary>
    ${[...g.cases].sort((a, b) => a.tier - b.tier || a.id.localeCompare(b.id)).map(c => {
      const v = c.verdict; const lr = c.latest_round;
      const st = (v || {}).state || "";
      return `<div class="ucrow ${esc(st)}">
        <span><span class="chip">tier ${c.tier}</span>${c.phase === 1 ? ` <span class="chip" title="production v1 scope">v1</span>` : ""}</span>
        <span><div class="t">${esc(c.title)}${c.parked ? ` <span class="amber small" title="${esc(c.parked)}">parked</span>` : ""}</div><div class="u" title="${esc(c.utterance)}">${esc(c.scenario)} · ${esc(clip(c.utterance, 110))}</div></span>
        <span>${v ? stateBadge(st) : `<span class="badge st-NONE">—</span>`}${v && v.stale ? `<span class="staledot" title="stale · measured on ${esc(v.sha)}"></span>` : ""}</span>
        <span>${v ? score(v.overall) : ""}</span>
        <span class="kk">${v ? `${v.kk.pass}/${v.kk.n} ${esc(v.kk.settled.toLowerCase())}<br><span class="faint">${esc(v.last_run || "")}</span>` : `<span class="faint">${esc(c.status || "")}</span>`}</span>
        <span class="small">${lr ? `<a href="${roundHref(lr.file, lr.idx)}">latest round →</a> <span class="muted">${ago(lr.started_at)}${lr.pending ? " · unjudged" : ""}</span>` : (v ? `<span class="faint">round file pruned · ledger only</span>` : "")}</span>
      </div>`; }).join("")}
  </details>`).join("");
}
