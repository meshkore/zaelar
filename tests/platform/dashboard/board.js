/* SCOREBOARD and SANDBOXES — two tabs of their own (operator, 2026-11-06: the home is numbers only; the tables
   that used to pile up under it live here).
     · scoreboard  — tests/use_cases/status.json folded per tier × locale, with the stale rows; beside it the
                     rounds list (judge.js) under the same sub-nav
     · sandboxes   — the kept use-case workspaces and the lab: locale, port, alive or kept, age, size, their round */
import { $, esc, api, ago, when, bytes, stateBadge, bar, empty, roundHref, fileHref, flag, subnav } from "./lib.js";

export const VERDICT_NAV = [["#/scoreboard", "Scoreboard"], ["#/rounds", "Rounds · the judge"]];

export function mountScoreboard(view) {
  view.innerHTML = `${subnav(VERDICT_NAV, "#/scoreboard")}
    <section class="panel" id="hBoard"><h2>Scoreboard <span class="sub" id="hBoardSub"></span></h2><div class="body">…</div></section>`;
  const tick = () => api("/api/scoreboard").then(board).catch(e => { $("hBoard").querySelector(".body").innerHTML = empty("scoreboard unreadable", String(e)); });
  tick();
  const timer = setInterval(tick, 20000);
  return () => clearInterval(timer);
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
      sb.stale.slice(0, 60).map(r => `<span class="chip st-${esc(r.state)}" title="${esc(r.last_run)} · ${esc(r.sha)}">${esc(r.id)}</span>`).join("")}${sb.stale.length > 60 ? `<span class="muted">+${sb.stale.length - 60}</span>` : ""}</div></details>` : ""}
    <div class="links"><a href="#/sets/usecases">the catalog, case by case →</a></div>`;
}

export function mountSandboxes(view) {
  view.innerHTML = `<section class="panel" id="hSandboxes"><h2>Sandboxes <span class="sub" id="hSandSub"></span></h2><div class="body">…</div></section>`;
  sandboxes();
  const timer = setInterval(sandboxes, 20000);
  return () => clearInterval(timer);
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
