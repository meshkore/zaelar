// ============================================================================
// memory/overview.js — the «Overview» tab (V2-808, V2-814, V2-815): the figures and charts of the brain — a row of
// headline numbers, the last 30 days of activity stacked by store, the concepts most present, how the space is
// split — and one card per store with its total, a sparkline and a one-line breakdown. A card opens IN PLACE to
// show its last 30 days and its breakdown (sources, types, sizes). Nothing about the machine is printed.
// Every number comes from `/api/memory/viewer/stats`: COUNTs on the server, never the length of a list.
// ============================================================================
import { h } from "../../core/dom.js?v=2";
import * as api from "../../services/api.js?v=2";
import { t } from "../../core/i18n.js?v=1";
import { num, bytes, ago, date, label } from "./format.js?v=2";

// The accent of each store's card: a palette token, so a profile swap repaints it.
const ACCENT = { memories: "--hb-accent", conversation: "--hb-accent", messages: "--hb-accent2", files: "--hb-warn",
                 contacts: "--hb-ok", agenda: "--hb-risk", apps: "--hb-muted", rules: "--hb-accent",
                 phrases: "--hb-accent2", events: "--hb-muted", vault: "--hb-risk" };
const FILE_TYPES = ["images", "videos", "audio", "documents", "other"];

const sum = (a) => (a || []).reduce((x, y) => x + (Number(y) || 0), 0);
const appName = (a) => (a.key === "results" ? t("memory.apps_results", { n: num(a.sheets) })
  : label("widgets.", a.key + ".name") || a.title || t("memory.app_unnamed"));
const platform = (k) => label("memory.platform_", k) || t("memory.platform_other");

// The big number of a card.
function total(s) {
  if (s.key === "apps") return s.pending ? "…" : bytes(s.total);
  if (s.key === "files") return bytes(s.bytes);
  return num(s.total);
}

// The one line under it.
function detail(s) {
  const p = s.parts || {};
  switch (s.key) {
    case "memories": return t("memory.store_memories_detail", { concepts: num(p.concepts), relations: num(p.relations) });
    case "conversation": return t("memory.store_conversation_detail", { days: num(p.days) })
      + (s.since ? " · " + t("memory.since", { date: date(s.since) }) : "");
    case "messages": return t("memory.store_messages_detail", { per_day: num(Math.round(sum(s.daily) / 30)),
                                                                sources: num(Object.keys(p).length) });
    case "files": {
      const ty = s.types || {};
      return t("memory.store_files_detail", { n: num(s.total), images: num(ty.images?.n), videos: num(ty.videos?.n) });
    }
    case "agenda": return t("memory.store_agenda_detail", { meetings: num(p.meetings), todo: num(p.todo), errands: num(p.errands) });
    case "apps": return s.pending ? t("memory.store_apps_measuring") : t("memory.store_apps_detail", { n: num((s.apps || []).length) });
    case "phrases": return t("memory.store_phrases_detail", { paraphrases: num(p.paraphrases) });
    default: return t(`memory.store_${s.key}_detail`);
  }
}

function note(s) {
  if (s.key === "vault") return { text: t("memory.note_encrypted"), cls: "" };
  const week = s.week ?? (s.daily ? sum(s.daily.slice(-7)) : 0);
  if (week) return { text: t("memory.note_week", { n: num(week) }), cls: "is-growing" };
  return { text: t("memory.note_stable"), cls: "is-ok" };
}

// The rows of the opened card: [label, value, share 0..1].
function breakdown(s) {
  const p = s.parts || {};
  const share = (v, all) => (all ? v / all : 0);
  switch (s.key) {
    case "memories": return [
      [t("memory.level_short_cap"), num(p.short), share(p.short, s.total)],
      [t("memory.level_long_cap"), num(p.long), share(p.long, s.total)],
      [t("memory.part_concepts"), num(p.concepts)], [t("memory.part_relations"), num(p.relations)]];
    case "conversation": return [
      [t("memory.part_sessions"), num(s.total)], [t("memory.part_days"), num(p.days)],
      [t("memory.part_turns"), num(p.turns)]];
    case "messages": {
      const rows = Object.entries(p).sort((a, b) => b[1] - a[1])
        .map(([k, v]) => [platform(k), num(v), share(v, s.total)]);
      return [...rows, [t("memory.part_size"), bytes(s.bytes)]];
    }
    case "files": {
      const ty = s.types || {};
      return FILE_TYPES.filter((k) => ty[k]?.n).sort((a, b) => ty[b].bytes - ty[a].bytes)
        .map((k) => [t("memory.files_" + k), `${num(ty[k].n)} · ${bytes(ty[k].bytes)}`, share(ty[k].bytes, s.bytes)]);
    }
    case "agenda": return [[t("memory.part_meetings"), num(p.meetings)], [t("memory.part_todo"), num(p.todo)],
                           [t("memory.part_errands"), num(p.errands)]];
    case "apps": return (s.apps || []).map((a) => [appName(a), bytes(a.bytes), share(a.bytes, s.total)]);
    case "phrases": return [[t("memory.part_phrases"), num(s.total)], [t("memory.part_paraphrases"), num(p.paraphrases)]];
    default: return [];
  }
}

function bars(daily) {
  const max = Math.max(1, ...daily);
  return h("div", { class: "mv-spark", role: "img", "aria-label": t("memory.last_30", { n: num(sum(daily)) }) },
    ...daily.map((v) => h("i", { class: v ? "" : "is-zero", style: { height: Math.max(3, (v / max) * 100) + "%" } })));
}

const miniBars = (daily) => h("span", { class: "mv-spark mv-spark--mini", "aria-hidden": "true" },
  ...daily.map((v) => h("i", { class: v ? "" : "is-zero", style: { height: Math.max(8, (v / Math.max(1, ...daily)) * 100) + "%" } })));

// ── the charts above the cards ──────────────────────────────────────────────────────────────────────────────
const ACTIVITY = ["memories", "conversation", "messages", "files"];

function kpis(stores, concepts) {
  const by = Object.fromEntries(stores.map((s) => [s.key, s]));
  const mem = by.memories || {}, msg = by.messages || {}, fil = by.files || {}, app = by.apps || {};
  const space = (Number(msg.bytes) || 0) + (Number(fil.bytes) || 0) + (Number(app.total) || 0);
  const items = [
    [t("memory.kpi_memories"), num(mem.total), t("memory.kpi_week", { n: num(mem.week || 0) })],
    [t("memory.kpi_concepts"), num(mem.parts?.concepts || concepts), t("memory.kpi_relations", { n: num(mem.parts?.relations) })],
    [t("memory.kpi_conversations"), num(by.conversation?.total), t("memory.kpi_days", { n: num(by.conversation?.parts?.days) })],
    [t("memory.kpi_messages"), num(msg.total), t("memory.kpi_week", { n: num(msg.week || 0) })],
    [t("memory.kpi_space"), bytes(space), t("memory.kpi_files", { n: num(fil.total) })],
  ];
  return h("div", { class: "mv-kpis" }, ...items.map(([k, v, sub]) =>
    h("div", { class: "hb-card mv-kpi" }, h("span", { class: "mv-kpi-k" }, k), h("b", { class: "mv-kpi-v" }, v),
      h("span", { class: "mv-kpi-sub" }, sub))));
}

function activity(stores) {
  const series = ACTIVITY.map((k) => stores.find((s) => s.key === k)).filter((s) => s?.daily);
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
  const first = new Date(Date.now() - (days - 1) * 86400000);
  return h("div", { class: "hb-card mv-chart" },
    h("div", { class: "mv-chart-head" }, h("p", { class: "hb-sectitle" }, t("memory.activity_title")),
      h("div", { class: "mv-legend-row" }, ...series.map((s) => h("span", {},
        h("i", { style: { background: `var(${ACCENT[s.key]})` } }), `${t("memory.store_" + s.key)} · ${num(sum(s.daily))}`)))),
    h("div", { class: "mv-act" }, ...cols),
    h("div", { class: "mv-act-axis" }, h("span", {}, date(first / 1000)), h("span", {}, t("memory.today"))));
}

function topConcepts(concepts, goTo) {
  if (!concepts?.length) return null;
  const top = concepts.slice(0, 10), max = Math.max(1, ...top.map((c) => c.count));
  const cap = (x) => (x ? x.charAt(0).toLocaleUpperCase() + x.slice(1) : "");
  return h("div", { class: "hb-card mv-chart" },
    h("div", { class: "mv-chart-head" }, h("p", { class: "hb-sectitle" }, t("memory.top_concepts")),
      h("button", { class: "hb-btn hb-btn--ghost hb-btn--sm", type: "button", onClick: () => goTo("graph") }, t("memory.see_graph"))),
    h("ol", { class: "mv-top" }, ...top.map((c, i) => h("li", {},
      h("span", { class: "mv-top-name" }, cap(c.label)), h("span", { class: "mv-top-n" }, num(c.count)),
      h("span", { class: "mv-fill" }, h("i", { style: { width: Math.max(4, (c.count / max) * 100) + "%",
        background: `var(${["--hb-accent", "--hb-accent2", "--hb-ok", "--hb-warn", "--hb-risk"][i % 5]})` } }))))));
}

function spaceSplit(stores) {
  const by = Object.fromEntries(stores.map((s) => [s.key, s]));
  const parts = [["messages", Number(by.messages?.bytes) || 0], ["files", Number(by.files?.bytes) || 0],
                 ["apps", Number(by.apps?.total) || 0]].filter(([, b]) => b > 0);
  const all = parts.reduce((a, [, b]) => a + b, 0);
  if (!all) return null;
  return h("div", { class: "hb-card mv-chart" },
    h("div", { class: "mv-chart-head" }, h("p", { class: "hb-sectitle" }, t("memory.space_title")),
      h("b", {}, bytes(all))),
    h("div", { class: "mv-split" }, ...parts.map(([k, b]) => h("i", { title: `${t("memory.store_" + k)} · ${bytes(b)}`,
      style: { width: (b / all) * 100 + "%", background: `var(${ACCENT[k]})` } }))),
    h("div", { class: "mv-legend-row" }, ...parts.map(([k, b]) => h("span", {},
      h("i", { style: { background: `var(${ACCENT[k]})` } }), `${t("memory.store_" + k)} · ${bytes(b)} · ${Math.round((b / all) * 100)}%`))));
}

function opened(s, goTo) {
  const rows = breakdown(s);
  return h("div", { class: "mv-store-more" },
    s.daily ? h("div", { class: "mv-more-chart" },
      h("p", { class: "hb-sectitle" }, t("memory.last_30", { n: num(sum(s.daily)) })), bars(s.daily)) : null,
    rows.length ? h("dl", { class: "mv-breakdown" }, ...rows.map(([k, v, f]) => h("div", { class: "mv-bd-row" },
      h("dt", {}, k), h("dd", {}, v),
      f != null ? h("span", { class: "mv-fill" }, h("i", { style: { width: Math.max(2, f * 100) + "%" } })) : null))) : null,
    s.key === "memories" ? h("button", { class: "hb-btn hb-btn--ghost hb-btn--sm", type: "button",
                                         onClick: (e) => { e.stopPropagation(); goTo("graph"); } }, t("memory.see_graph")) : null);
}

export function Overview({ goTo }) {
  let grid, sub, charts, timer = null, concepts = null;
  const open = new Set();
  let last = null;

  function card(s) {
    const nt = note(s);
    const can = !!(s.daily || breakdown(s).length);
    const isOpen = can && open.has(s.key);
    const toggle = () => { if (open.has(s.key)) open.delete(s.key); else open.add(s.key); paint(); };
    return h("div", { class: "hb-card mv-store" + (isOpen ? " is-open" : ""), "data-store": s.key,
                      style: { "--mv-accent": `var(${ACCENT[s.key] || "--hb-accent"})` } },
      h(can ? "button" : "div", { class: "mv-store-face", type: can ? "button" : null,
                                  "aria-expanded": can ? String(isOpen) : null, onClick: can ? toggle : null },
        h("span", { class: "mv-store-head" }, h("span", { class: "mv-store-name" }, t(`memory.store_${s.key}`)),
          h("i", { class: "mv-store-dot" })),
        h("span", { class: "mv-store-total" }, total(s)),
        h("span", { class: "mv-store-detail" }, detail(s)),
        s.daily && !isOpen ? miniBars(s.daily) : null,
        h("span", { class: "mv-store-note " + nt.cls }, nt.text)),
      isOpen ? opened(s, goTo) : null);
  }

  function paint() {
    if (!last) return;
    const stores = last.stores || [];
    charts.replaceChildren(kpis(stores, concepts?.length || 0),
      h("div", { class: "mv-charts" }, ...[activity(stores), topConcepts(concepts, goTo), spaceSplit(stores)].filter(Boolean)));
    grid.replaceChildren(...stores.map(card));
  }

  async function load() {
    const [body, g] = await Promise.all([api.memoryViewer("stats"),
                                         api.memoryViewer("graph", { days: 0, budget: 50, lanes: "own" })]);
    concepts = g?.concepts || concepts;
    if (!body) { sub.textContent = t("memory.load_error"); return; }
    last = body;
    const stores = body.stores || [];
    const size = stores.reduce((a, s) => a + (Number(s.bytes) || 0) + (s.key === "apps" ? Number(s.total) || 0 : 0), 0);
    sub.textContent = t("memory.ov_sub", { size: bytes(size), ago: ago(body.counted_at) });
    paint();
    clearTimeout(timer);
    if (stores.some((s) => s.pending)) timer = setTimeout(load, 2500);   // the app folders are still being measured
  }

  const el = h("div", { class: "mv-overview" },
    h("div", { class: "mv-ov-title" }, h("h2", {}, () => t("memory.ov_title")), h("p", { class: "mv-muted", ref: (x) => (sub = x) })),
    h("div", { class: "mv-ov-charts", ref: (x) => (charts = x) }),
    h("p", { class: "hb-sectitle mv-ov-stores" }, () => t("memory.stores_title")),
    h("div", { class: "mv-stores", ref: (x) => (grid = x) }));

  let loaded = false;
  return { el, activate() { if (!loaded) { loaded = true; load(); } }, deactivate() {}, refresh() { if (loaded) load(); } };
}
