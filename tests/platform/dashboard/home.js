/* HOME — numbers only (operator, 2026-11-06). Three boxes, one per layer:
     · UNIT       — the last sweep of tests/watchdog.py: how many, green, red, hung
     · BENCHES    — how many benches, how many with a run on disk, green / red by the bench's own criterion,
                    «no threshold» where a score has none (never a colour invented)
     · USE CASES  — ES | US side by side: total (the catalog's `completable` segment), PASS, FAIL, INFRA apart;
                    below, one row per THEME with «pass/total» in each language
   Above them, ONE line when somebody is testing right now, which opens the live screen (#/live). Nothing else:
   the scoreboard, the sandboxes and the rounds have their own tabs. The server computes every number
   (`/api/home`, tests/platform/observatory_data.py); this file only paints. */
import { $, esc, clip, api, ago, when, dur, verdictBadge, empty, flag } from "./lib.js";

export function mount(view) {
  view.innerHTML = `
    <div id="hLive"></div>
    <section class="grid3" id="hBoxes"><section class="panel"><div class="empty">loading…</div></section></section>`;
  const tick = () => paint();
  tick();
  const timer = setInterval(tick, 5000);
  return () => clearInterval(timer);
}

async function paint() {
  let d;
  try { d = await api("/api/home"); } catch (e) { $("hBoxes").innerHTML = `<section class="panel">${empty("home unreadable", String(e))}</section>`; return; }
  live(d.live || []);
  $("hBoxes").innerHTML = unitBox(d.unit) + benchBox(d.benches) + ucBox(d.use_cases);
}

/* ─── the one-line notice: somebody is testing now → the live screen ───── */
function live(rows) {
  const host = $("hLive");
  if (!rows.length) { host.innerHTML = ""; return; }
  const who = rows.map(r => `<b>${esc(r.actor)}</b> <span class="chip">${esc(r.suite)}</span> <span class="muted">${r.done} / ${r.total || "?"}${
    r.current && r.current.label ? ` · ${esc(clip(r.current.label, 60))}` : ""}</span>`).join(" <span class=\"faint\">·</span> ");
  host.innerHTML = `<a class="notice" href="#/live"><span class="livedot"></span><span class="nt">${rows.length === 1 ? "A session is testing right now" : `${rows.length} sessions are testing right now`}</span><span class="nw">${who}</span><span class="right">watch it →</span></a>`;
}

/* ─── UNIT ─────────────────────────────────────────────────────────────── */
function unitBox(u) {
  if (!u || !u.last) return box("Unit tests", "", empty("no sweep on disk", "tests/watchdog.py writes tests/runs/watchdog-*.json"), "#/sets/unit");
  const l = u.last;
  return box("Unit tests", `${when(l.at)} · ${ago(l.at)} · ${dur(l.seconds)}`, `
    ${big(u.total, "tests in the last sweep")}
    <div class="numrow">
      ${num(u.passed, "green", "ok")}
      ${num(u.failed, "red", u.failed ? "bad" : "muted")}
      ${u.hung ? num(u.hung, "hung", "amber") : ""}
      ${u.skipped ? num(u.skipped, "skipped", "muted") : ""}
    </div>
    <div class="muted small">${verdictBadge(l.verdict)} ${l.targets} target${l.targets === 1 ? "" : "s"}</div>`, "#/sets/unit");
}

/* ─── BENCHES ──────────────────────────────────────────────────────────── */
function benchBox(b) {
  if (!b || !b.n) return box("Benches", "", empty("no bench declared"), "#/sets/benches");
  return box("Benches", `${b.with_run} of ${b.n} with a run on disk`, `
    ${big(b.n, "module benches")}
    <div class="numrow">
      ${num(b.green, "green", "ok")}
      ${num(b.red, "red", b.red ? "bad" : "muted")}
      ${num(b.no_threshold, "no threshold", "muted")}
      ${num(b.no_run, "no run", "muted")}
    </div>
    <div class="muted small">green / red only where the bench carries its own criterion; a bare score stays «no threshold»</div>`, "#/sets/benches");
}

/* ─── USE CASES ─────────────────────────────────────────────────────────── */
function ucBox(u) {
  if (!u || !u.locales) return box("Use cases", "", empty("no catalog"), "#/sets/usecases");
  const L = u.locales;
  const col = loc => {
    const c = L[loc] || {};
    return `<div class="uccol">
      <div class="uchead">${flag(loc)}</div>
      ${big(c.total || 0, "completable")}
      <div class="numrow">
        ${num(c.PASS || 0, "pass", "ok")}
        ${num(c.FAIL || 0, "fail", c.FAIL ? "bad" : "muted")}
        ${num(c.INFRA || 0, "infra", c.INFRA ? "amber" : "muted")}
        ${c.CAPPED ? num(c.CAPPED, "capped", "blue") : ""}
        ${c.never ? num(c.never, "never run", "faint") : ""}
      </div>
      <div class="faint small">apart: ${(c.excluded || {}).credentials || 0} need credentials · ${(c.excluded || {}).capability || 0} need a capability</div>
    </div>`;
  };
  const cell = c => c && c.total ? `<span class="${c.PASS === c.total ? "ok" : c.PASS ? "" : "muted"}"><b>${c.PASS}</b>/${c.total}</span>${
    c.INFRA ? ` <span class="amber small" title="INFRA — not measured">${c.INFRA}i</span>` : ""}` : `<span class="faint">—</span>`;
  const rows = (u.themes || []).map(t => `<tr><td class="th" title="${esc(t.hint)}">${esc(t.label)}</td><td>${cell(t.es)}</td><td>${cell(t.us)}</td></tr>`).join("");
  return box("Use cases", `ledger ${esc(u.updated || "—")} · HEAD ${esc(u.head || "—")}`, `
    <div class="uccols">${col("es")}${col("us")}</div>
    <table class="themes"><thead><tr><th>theme</th><th>${flag("es")}</th><th>${flag("us")}</th></tr></thead><tbody>${rows}</tbody></table>
    <div class="legend"><b>pass/total</b> per theme · <span class="amber">n i</span> = INFRA, not measured, not red · the denominator is the catalog's <code>${esc(u.segment || "completable")}</code> segment; the state is the accumulated ledger, never one evening's batch</div>`,
    "#/sets/usecases", `<a href="#/scoreboard">scoreboard →</a>`);
}

/* ─── pieces ───────────────────────────────────────────────────────────── */
const big = (n, label) => `<div class="bignum">${esc(n)}</div><div class="biglabel">${esc(label)}</div>`;
const num = (n, label, cls) => `<div class="num ${esc(cls)}"><b>${esc(n)}</b><span>${esc(label)}</span></div>`;
function box(title, sub, body, href, more = "") {
  return `<section class="panel"><h2>${esc(title)} <span class="sub">${sub}</span></h2><div class="body">${body}</div>
    <div class="links"><a href="${esc(href)}">the rows →</a>${more ? ` · ${more}` : ""}</div></section>`;
}
