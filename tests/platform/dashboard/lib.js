/* Shared helpers of the Observatory's screens: fetch, escape, formats, badges. No state lives here. */
export const $ = id => document.getElementById(id);
export const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
export const clip = (s, n) => { s = String(s == null ? "" : s); return s.length > n ? s.slice(0, n) + "…" : s; };

export async function api(path) {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}

/* ─── time ─────────────────────────────────────────────────────────────── */
export function ago(epochS) {
  if (!epochS) return "—";
  const d = Math.max(0, Date.now() / 1000 - epochS);
  if (d < 60) return `${Math.round(d)} s ago`;
  if (d < 3600) return `${Math.round(d / 60)} min ago`;
  if (d < 86400) return `${(d / 3600).toFixed(d < 36000 ? 1 : 0)} h ago`;
  return `${Math.round(d / 86400)} d ago`;
}
export function when(epochS) {
  if (!epochS) return "—";
  const d = new Date(epochS * 1000);
  const p = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
export function dur(seconds) {
  if (seconds == null || isNaN(seconds)) return "—";
  const s = Math.max(0, Math.round(seconds));
  if (s < 90) return `${s} s`;
  if (s < 5400) return `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`;
  return `${(s / 3600).toFixed(1)} h`;
}
export function ms(x) { return x == null ? "—" : x < 1500 ? `${Math.round(x)} ms` : `${(x / 1000).toFixed(1)} s`; }
export function bytes(n) {
  if (!n) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n < 10 && i ? 1 : 0)} ${u[i]}`;
}

/* ─── badges ───────────────────────────────────────────────────────────── */
export function stateBadge(st) {
  const s = String(st || "—").toUpperCase();
  return `<span class="badge st-${esc(s)}">${esc(s)}</span>`;
}
export function verdictBadge(v) {
  const s = String(v || "—");
  const cls = s === "ok" || s === "passed" ? "st-PASS" : s === "failed" ? "st-FAIL" : s === "hung" ? "st-INFRA" : "st-NONE";
  return `<span class="badge ${cls}">${esc(s)}</span>`;
}
export function trend(delta, { invert = false, unit = "" } = {}) {
  if (delta == null || isNaN(delta)) return `<span class="trend flat">no previous run</span>`;
  if (delta === 0) return `<span class="trend flat">= same as before</span>`;
  const good = invert ? delta < 0 : delta > 0;
  return `<span class="trend ${good ? "up" : "down"}">${delta > 0 ? "▲" : "▼"} ${Math.abs(delta)}${esc(unit)} vs previous</span>`;
}
export function score(n, max = 5) {
  if (n == null) return `<span class="score none">—</span>`;
  const cls = n >= 4 ? "good" : n >= 3 ? "mid" : "bad";
  return `<span class="score ${cls}">${esc(n)}<small>/${max}</small></span>`;
}
export function flag(locale) { return locale === "us" ? "🇺🇸 US" : locale === "es" ? "🇪🇸 ES" : esc(locale || "—"); }
export function bar(parts, total) {
  /* parts: [{n, cls}] → stacked bar */
  if (!total) return `<div class="stack empty"></div>`;
  return `<div class="stack">${parts.filter(p => p.n).map(p =>
    `<i class="${esc(p.cls)}" style="width:${(100 * p.n / total).toFixed(2)}%" title="${esc(p.cls)} ${p.n}"></i>`).join("")}</div>`;
}
export function subnav(items, on) {
  /* items: [[href, label]] → the pill row the test-sets screen uses, with `on` lit */
  return `<nav class="subnav">${items.map(([h, l]) => `<a href="${esc(h)}" class="${h === on ? "on" : ""}">${esc(l)}</a>`).join("")}</nav>`;
}
export function empty(title, hint) {
  return `<div class="empty"><b>${esc(title)}</b>${hint ? esc(hint) : ""}</div>`;
}
export const roundHref = (file, idx = 0) => `#/round/${encodeURIComponent(file)}/${idx}`;
export const brainHref = (file, idx = 0, turn = 0) => `#/brain/${encodeURIComponent(file)}/${idx}/${turn}`;
export const runHref = id => `#/run/${encodeURIComponent(id)}`;
export const fileHref = rel => `/runs/${rel.split("/").map(encodeURIComponent).join("/")}`;
