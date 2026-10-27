// ============================================================================
// memory/overview.js — the «Overview» tab (V2-808, V2-814, V2-815, V2-816): what the brain keeps, as ONE page that
// reads top to bottom and says each number once.
//
//   1. Totals — one tile per store the operator thinks in (memories, conversations, messages, files, contacts,
//      agenda, space), with the week's growth under it.
//   2. Charts — the last 30 days of activity stacked by store; the concepts most present (the only place the concept
//      and relation counts appear); how the space is split (the only place sizes per store appear).
//   3. Breakdown — what each store is made of (layers, sources, types, apps) and the smaller stores, which have no
//      tile. A figure shown above is never repeated here.
//
// A plain page on purpose: no card that opens, no inner scroller — the viewer lets the DOCUMENT scroll while this
// tab is on (MemoryMap.js), so a full-page capture stitches it cleanly. Every number comes from
// `/api/memory/viewer/stats` (COUNTs on the server) and the concepts from `/api/memory/viewer/graph`. Nothing about
// the machine is printed.
// ============================================================================
import { h } from "../../core/dom.js?v=2";
import * as api from "../../services/api.js?v=2";
import { t } from "../../core/i18n.js?v=1";
import { num, bytes, ago, date, label } from "./format.js?v=2";

// The colour of each store: a palette token, so a profile swap repaints it.
const ACCENT = { memories: "--hb-accent", conversation: "--hb-accent2", messages: "--hb-ok", files: "--hb-warn",
                 apps: "--hb-muted" };
const FILE_TYPES = ["images", "videos", "audio", "documents", "other"];
const ACTIVITY = ["memories", "conversation", "messages", "files"];
const BAR = ["--hb-accent", "--hb-accent2", "--hb-ok", "--hb-warn", "--hb-risk"];

const sum = (a) => (a || []).reduce((x, y) => x + (Number(y) || 0), 0);
const week = (s) => s?.week ?? (s?.daily ? sum(s.daily.slice(-7)) : 0);
const cap = (x) => (x ? x.charAt(0).toLocaleUpperCase() + x.slice(1) : "");
const appName = (a) => (a.key === "results" ? t("memory.apps_results", { n: num(a.sheets) })
  : label("widgets.", a.key + ".name") || a.title || t("memory.app_unnamed"));
const platform = (k) => label("memory.platform_", k) || t("memory.platform_other");
const swatch = (k) => h("i", { class: "mv-swatch", style: { background: `var(${ACCENT[k] || "--hb-accent"})` } });

// ── 1. totals ───────────────────────────────────────────────────────────────────────────────────────────────
function totals(by) {
  const space = (Number(by.messages?.bytes) || 0) + (Number(by.files?.bytes) || 0) + (Number(by.apps?.total) || 0);
  const grow = (s) => t("memory.kpi_week", { n: num(week(s)) });
  const ag = by.agenda?.parts || {};
  const tiles = [
    ["memories", num(by.memories?.total), grow(by.memories)],
    ["conversation", num(by.conversation?.total), t("memory.kpi_days", { n: num(by.conversation?.parts?.days) })],
    ["messages", num(by.messages?.total), grow(by.messages)],
    ["files", num(by.files?.total), grow(by.files)],
    ["contacts", num(by.contacts?.total), ""],
    ["agenda", num(by.agenda?.total), t("memory.kpi_meetings", { n: num(ag.meetings) })],
    ["space", by.apps?.pending ? "…" : bytes(space), ""],
  ];
  return h("section", { class: "mv-totals", "aria-label": t("memory.totals_title") },
    ...tiles.map(([k, v, sub]) => h("div", { class: "hb-card mv-kpi", "data-store": k },
      h("span", { class: "mv-kpi-k" }, k === "space" ? t("memory.kpi_space") : t("memory.store_" + k)),
      h("b", { class: "mv-kpi-v" }, v),
      h("span", { class: "mv-kpi-sub" }, sub || " "))));
}

// ── 2. charts ───────────────────────────────────────────────────────────────────────────────────────────────
function activity(by) {
  const series = ACTIVITY.map((k) => by[k]).filter((s) => s?.daily);
  if (!series.length) return null;
  const days = series[0].daily.length;
  // each store is scaled to its own peak: a message flood must not flatten the memories next to it
  const peak = series.map((s) => Math.max(1, ...s.daily));
  const cols = [];
  for (let d = 0; d < days; d++) {
    const day = new Date(Date.now() - (days - 1 - d) * 86400000);
    const tip = [day.toLocaleDateString(), ...series.map((s) => `${t("memory.store_" + s.key)}: ${num(s.daily[d])}`)].join("\n");
    cols.push(h("div", { class: "mv-act-col", title: tip },
      ...series.map((s, i) => h("i", { style: { height: (s.daily[d] / peak[i]) * (100 / series.length) + "%",
                                                  background: `var(${ACCENT[s.key]})` } }))));
  }
  return h("div", { class: "hb-card mv-chart mv-chart--activity" },
    h("div", { class: "mv-chart-head" }, h("p", { class: "hb-sectitle" }, t("memory.activity_title")),
      // names only: a 30-day sum beside a store's name reads as its total, and the total is already a tile
      h("div", { class: "mv-legend-row" }, ...series.map((s) => h("span", {}, swatch(s.key), t("memory.store_" + s.key))))),
    h("div", { class: "mv-act" }, ...cols),
    h("div", { class: "mv-act-axis" }, h("span", {}, date((Date.now() - (days - 1) * 86400000) / 1000)),
      h("span", {}, t("memory.today"))));
}

function concepts(list, parts, goTo) {
  if (!list?.length) return null;
  const top = list.slice(0, 10), max = Math.max(1, ...top.map((c) => c.count));
  return h("div", { class: "hb-card mv-chart" },
    h("div", { class: "mv-chart-head" },
      h("p", { class: "hb-sectitle" }, t("memory.top_concepts")),
      h("button", { class: "hb-btn hb-btn--ghost hb-btn--sm", type: "button", onClick: () => goTo("graph") }, t("memory.see_graph"))),
    h("p", { class: "mv-muted" }, t("memory.concepts_line", { concepts: num(parts?.concepts), relations: num(parts?.relations) })),
    h("ol", { class: "mv-rows" }, ...top.map((c, i) => row(cap(c.label), num(c.count), c.count / max, BAR[i % BAR.length]))));
}

function space(by) {
  const parts = [["messages", Number(by.messages?.bytes) || 0], ["files", Number(by.files?.bytes) || 0],
                 ["apps", Number(by.apps?.total) || 0]].filter(([, b]) => b > 0);
  const all = parts.reduce((a, [, b]) => a + b, 0);
  if (!all) return null;
  return h("div", { class: "hb-card mv-chart" },
    h("p", { class: "hb-sectitle" }, t("memory.space_title")),
    h("div", { class: "mv-split" }, ...parts.map(([k, b]) => h("i", { title: `${t("memory.store_" + k)} · ${bytes(b)}`,
      style: { width: (b / all) * 100 + "%", background: `var(${ACCENT[k]})` } }))),
    h("div", { class: "mv-legend-row" }, ...parts.map(([k, b]) => h("span", {}, swatch(k),
      `${t("memory.store_" + k)} · ${bytes(b)} · ${Math.round((b / all) * 100)}%`))));
}

// ── 3. breakdown ────────────────────────────────────────────────────────────────────────────────────────────
// One row: a label, its value and, when it is a share of something, a bar.
function row(k, v, share, color) {
  return h("li", { class: "mv-row" }, h("span", { class: "mv-row-k" }, k), h("span", { class: "mv-row-v" }, v),
    share != null ? h("span", { class: "mv-fill" }, h("i", { style: { width: Math.max(2, share * 100) + "%",
                                                                       background: color ? `var(${color})` : null } })) : null);
}
const panel = (key, title, rows, accent) => (rows.length ? h("div", { class: "hb-card mv-panel", "data-store": key },
  h("p", { class: "mv-panel-title" }, accent ? swatch(accent) : null, title),
  h("ul", { class: "mv-rows" }, ...rows)) : null);

// The apps that keep the most, and the rest as one line: a long tail of tiny folders is not information.
const APPS_SHOWN = 6;
function appRows(apps) {
  const list = [...(apps?.apps || [])].sort((a, b) => b.bytes - a.bytes);
  const rows = list.slice(0, APPS_SHOWN).map((a) => row(appName(a), bytes(a.bytes), apps.total ? a.bytes / apps.total : 0, ACCENT.apps));
  const rest = list.slice(APPS_SHOWN);
  if (rest.length) rows.push(row(t("memory.apps_rest", { n: num(rest.length) }), bytes(rest.reduce((x, a) => x + a.bytes, 0))));
  return rows;
}

function breakdown(by) {
  const share = (v, all) => (all ? v / all : 0);
  const mem = by.memories, conv = by.conversation, msg = by.messages, fil = by.files, ag = by.agenda, apps = by.apps;
  const mp = mem?.parts || {}, ap = ag?.parts || {};
  const ty = fil?.types || {};
  const panels = [
    panel("memories", t("memory.store_memories"), mem ? [
      row(t("memory.level_short_cap"), num(mp.short), share(mp.short, mem.total), ACCENT.memories),
      row(t("memory.level_long_cap"), num(mp.long), share(mp.long, mem.total), ACCENT.memories)] : [], "memories"),
    panel("conversation", t("memory.store_conversation"), conv ? [
      ...(conv.parts?.turns ? [row(t("memory.part_turns"), num(conv.parts.turns))] : []),
      ...(conv.since ? [row(t("memory.part_since"), date(conv.since))] : [])] : [], "conversation"),
    panel("messages", t("memory.store_messages"), Object.entries(msg?.parts || {}).sort((a, b) => b[1] - a[1])
      .map(([k, v]) => row(platform(k), num(v), share(v, msg.total), ACCENT.messages)), "messages"),
    panel("files", t("memory.store_files"), FILE_TYPES.filter((k) => ty[k]?.n).sort((a, b) => ty[b].bytes - ty[a].bytes)
      .map((k) => row(t("memory.files_" + k), `${num(ty[k].n)} · ${bytes(ty[k].bytes)}`, share(ty[k].bytes, fil.bytes), ACCENT.files)), "files"),
    panel("agenda", t("memory.store_agenda"), ag ? [row(t("memory.part_todo"), num(ap.todo)),
      row(t("memory.part_errands"), num(ap.errands))] : []),
    panel("apps", t("memory.store_apps"), apps?.pending ? [row(t("memory.store_apps_measuring"), "…")] : appRows(apps), "apps"),
    panel("other", t("memory.other_stores"), [
      ...["rules", "phrases"].filter((k) => by[k]).map((k) => row(t("memory.store_" + k), num(by[k].total))),
      ...(by.phrases?.parts?.paraphrases ? [row(t("memory.part_paraphrases"), num(by.phrases.parts.paraphrases))] : []),
      ...["events", "vault"].filter((k) => by[k]).map((k) => row(t("memory.store_" + k), num(by[k].total)))]),
  ].filter(Boolean);
  return h("section", { class: "mv-breakdown-grid", "aria-label": t("memory.breakdown_title") }, ...panels);
}

export function Overview({ goTo }) {
  let page, sub, timer = null, conceptList = null;

  async function load() {
    const [body, g] = await Promise.all([api.memoryViewer("stats"),
                                         api.memoryViewer("graph", { days: 0, budget: 50, lanes: "own" })]);
    conceptList = g?.concepts || conceptList;
    if (!body) { sub.textContent = t("memory.load_error"); return; }
    const stores = body.stores || [];
    const by = Object.fromEntries(stores.map((s) => [s.key, s]));
    sub.textContent = t("memory.ov_counted", { ago: ago(body.counted_at) });
    const side = [concepts(conceptList, by.memories?.parts, goTo), space(by)].filter(Boolean);
    page.replaceChildren(
      totals(by),
      h("section", { class: "mv-charts" }, ...[activity(by), side.length ? h("div", { class: "mv-charts-side" }, ...side) : null]
        .filter(Boolean)),
      h("p", { class: "hb-sectitle mv-ov-section" }, t("memory.breakdown_title")),
      breakdown(by));
    clearTimeout(timer);
    if (stores.some((s) => s.pending)) timer = setTimeout(load, 2500);   // the app folders are still being measured
  }

  const el = h("div", { class: "mv-overview" },
    h("div", { class: "mv-ov-title" }, h("h2", {}, () => t("memory.ov_title")), h("p", { class: "mv-muted", ref: (x) => (sub = x) })),
    h("div", { class: "mv-ov-page", ref: (x) => (page = x) }));

  let loaded = false;
  return { el, activate() { if (!loaded) { loaded = true; load(); } }, deactivate() {}, refresh() { if (loaded) load(); } };
}
