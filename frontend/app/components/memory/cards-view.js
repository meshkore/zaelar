// ============================================================================
// memory/cards-view.js — the «Cards» tab of the memory viewer: the ORIGINAL map of the memory (V2-014), restored
// by the operator's request (V2-815) inside the tabbed viewer, now BOUNDED.
//
//   · SLOTS     — the memory AS IT IS STORED: three side-by-side columns (STATE · SHORT · LONG); every memory is
//                 a card with its text, score, weight, accesses and date. Zoom (wheel) + pan (drag).
//   · CONCEPTS  — the memory AS IT IS ORGANISED: one concept map per layer, concepts sized by how many memories
//                 touch them, wired by co-occurrence.
//
// The limit is what makes it safe to keep: the server returns at most `tier.rows` of the NEWEST cards per layer
// (and caps that again), the concept maps at most a ring's worth of concepts, and the text of a card is cut on
// the server. Growth of the store never grows what this tab paints; the header says how many are shown of how
// many there are. Live: `memory.updated` asks the visible tab to refresh, and touched cards light up.
// ============================================================================
import { h, raw } from "../../core/dom.js?v=2";
import * as api from "../../services/api.js?v=2";
import { FIT_ICON, REFRESH_ICON, PIN_ICON } from "../../lib/icons.js?v=1";
import { t } from "../../core/i18n.js?v=1";
import { num as fmtNum } from "./format.js?v=2";

const SVGNS = "http://www.w3.org/2000/svg";

// ---- layout constants (px, world-space pre-scale) ----
const PAD = 26, NODE_H = 98, GX = 14, GY = 14;
const NODE_W_MIN = 150;
const IPAD = 14;
const HEAD_H = 56;
const COL_GAP = 34;

const ZONES = [
  { key: "state", frac: 0.10, title: "memory.zone_state", sub: "memory.zone_state_sub", accent: "var(--hb-neutral)" },
  { key: "short", frac: 0.20, title: "memory.zone_short", sub: "memory.zone_short_sub", accent: "var(--hb-accent2)" },
  { key: "long",  frac: 0.70, title: "memory.zone_long", sub: "memory.zone_long_sub", accent: "var(--hb-accent)" },
];

function computeGeom(viewW) {
  const worldW = Math.max(720, viewW || 1200);
  const usable = worldW - PAD * 2 - COL_GAP * (ZONES.length - 1);
  let x = PAD; const geom = {};
  for (const z of ZONES) {
    const w = Math.max(NODE_W_MIN + IPAD * 2, Math.round(usable * z.frac));
    const innerW = w - IPAD * 2;
    const cols = Math.max(1, Math.floor((innerW + GX) / (NODE_W_MIN + GX)));
    const nodeW = Math.floor((innerW - (cols - 1) * GX) / cols);
    geom[z.key] = { x, w, cols, nodeW };
    x += w + COL_GAP;
  }
  return { geom, worldW: x - COL_GAP + PAD };
}

function fmtDate(sec) {
  if (!sec) return "";
  const d = new Date(sec * 1000), p = (n) => String(n).padStart(2, "0");
  return `${p(d.getDate())}/${p(d.getMonth() + 1)} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
const num = (v, dp = 2) => (typeof v === "number" ? v.toFixed(dp) : "—");

function stateItems(s) {
  s = s || {};
  const arr = (v) => (Array.isArray(v) && v.length ? v.join(" · ") : "");
  return [
    { label: t("memory.field_mission"), val: s.mission },
    { label: t("memory.field_operator"), val: s.operator_name },
    { label: t("memory.field_treatment"), val: s.treatment },
    { label: t("memory.field_location"), val: s.location },
    { label: t("memory.field_language"), val: s.language },
    { label: t("memory.field_assistant"), val: s.assistant_name },
    { label: t("memory.field_open_widgets"), val: arr(s.open_widgets) },
    { label: t("memory.field_activity"), val: arr(s.activity) },
    { label: t("memory.field_recent"), val: arr(s.recent) },
    { label: t("memory.field_topics"), val: arr(s.topics) },
  ];
}

const OP_CLS = {
  write: "pulse-new", episode: "pulse-new",
  reinforce: "pulse-upd", state: "pulse-upd", consolidate: "pulse-upd", link: "pulse-upd",
  migrate_inbox: "pulse-upd", pin: "pulse-upd", unpin: "pulse-upd",
  query: "pulse-qry",
};
const PULSE_CLASSES = ["pulse-new", "pulse-upd", "pulse-qry"];
const PULSE_MS = 4200;

export function CardsView({ tier }) {
  let viewportEl, worldEl, nodesEl, emptyEl, countsEl, slotsBtn, conceptsBtn;
  let worldH = 400, worldW = 1200;
  let lastData = null;
  let mode = "slots";
  let active = false, fitted = false;
  const pulses = new Map();
  const view = { scale: 0.9, tx: PAD, ty: PAD };
  const edgesSvg = document.createElementNS(SVGNS, "svg");
  edgesSvg.setAttribute("class", "mm-edges");

  const applyView = () => {
    if (worldEl) worldEl.style.transform = `translate(${view.tx}px,${view.ty}px) scale(${view.scale})`;
  };

  function fitView() {
    if (!viewportEl) return;
    const r = viewportEl.getBoundingClientRect();
    if (r.width < 20 || r.height < 20) return;
    view.scale = Math.max(0.3, Math.min(r.width / worldW, 1));
    view.tx = Math.max(0, (r.width - worldW * view.scale) / 2);
    view.ty = PAD;
    applyView();
    fitted = true;
  }

  function memCard(m, x, y, w) {
    const el = document.createElement("div");
    el.className = "mm-node k-" + String(m.kind || "").replace(/[^a-z0-9_]/gi, "");
    if (m.pinned) el.classList.add("pinned");
    el.dataset.mid = String(m.id);
    el.style.left = x + "px"; el.style.top = y + "px"; el.style.width = w + "px";
    el.title = `${m.kind} · ${m.level}\n${m.text || ""}\n\n${t("memory.score")} ${num(m.importance)} · ${t("memory.weight")} ${num(m.weight)} · ${t("memory.accesses")} ${m.access_count || 0}` +
      `\n${t("memory.created")} ${fmtDate(m.created)} · ${t("memory.seen")} ${fmtDate(m.last_access)}` +
      (m.ttl_days != null ? ` · ${t("memory.ttl")} ${m.ttl_days}d` : "");
    const tx = document.createElement("div"); tx.className = "mm-tx"; tx.textContent = m.text || "";
    const meta = document.createElement("div"); meta.className = "mm-meta";
    const chip = (s, cls) => { const c = document.createElement("span"); c.className = "mm-chip" + (cls ? " " + cls : ""); c.textContent = s; return c; };
    meta.appendChild(chip(m.kind || "?", "kind"));
    meta.appendChild(chip("s·" + num(m.importance)));
    meta.appendChild(chip("×" + (m.access_count || 0)));
    if (m.pinned) { const p = document.createElement("span"); p.className = "mm-chip pin"; p.innerHTML = PIN_ICON; meta.appendChild(p); }
    const wrap = document.createElement("div"); wrap.className = "mm-wbar";
    const fill = document.createElement("i"); fill.style.width = Math.round(Math.max(0, Math.min(1, m.weight || 0)) * 100) + "%";
    wrap.appendChild(fill);
    const date = document.createElement("div"); date.className = "mm-date"; date.textContent = fmtDate(m.updated || m.created);
    el.append(tx, meta, wrap, date);
    return el;
  }

  function stateCard(it, x, y, w) {
    const el = document.createElement("div");
    el.className = "mm-node state"; el.style.left = x + "px"; el.style.top = y + "px"; el.style.width = w + "px";
    const empty = it.val == null || it.val === "";
    if (empty) el.classList.add("empty");
    el.title = it.label + ": " + (empty ? t("memory.empty_paren") : it.val);
    const lb = document.createElement("div"); lb.className = "mm-slabel"; lb.textContent = it.label;
    const vl = document.createElement("div"); vl.className = "mm-sval"; vl.textContent = empty ? "—" : String(it.val);
    el.append(lb, vl);
    return el;
  }

  function zoneColumn(z, x, y, w, height, count) {
    const b = document.createElement("div");
    b.className = "mm-band k-" + z.key;
    b.style.left = x + "px"; b.style.top = y + "px";
    b.style.width = w + "px"; b.style.height = height + "px";
    b.style.borderTopColor = z.accent;
    const lab = document.createElement("div"); lab.className = "mm-zlabel";
    const head = document.createElement("div"); head.className = "mm-zhead";
    const titleEl = document.createElement("span"); titleEl.className = "mm-ztitle"; titleEl.textContent = t(z.title);
    head.appendChild(titleEl);
    if (count !== "") { const c = document.createElement("span"); c.className = "mm-zcount"; c.textContent = count; head.appendChild(c); }
    const sub = document.createElement("span"); sub.className = "mm-zsub"; sub.textContent = t(z.sub);
    lab.append(head, sub);
    b.appendChild(lab);
    return b;
  }

  // The count printed on a column: «shown / total» once the store is bigger than what this device draws.
  const shownOf = (shown, total) => (total > shown ? `${fmtNum(shown)} / ${fmtNum(total)}` : fmtNum(shown));

  function renderSlots(data) {
    const vw = viewportEl ? viewportEl.getBoundingClientRect().width : 1200;
    const { geom, worldW: ww } = computeGeom(vw);
    worldW = ww;
    const gridTop = PAD + HEAD_H;
    const c = data.counts || {};
    let maxBottom = PAD;
    for (const z of ZONES) {
      const g = geom[z.key];
      const items = z.key === "state" ? stateItems(data.state) : ((data.layers && data.layers[z.key]) || []);
      const n = items.length;
      const rows = Math.max(1, Math.ceil(n / g.cols));
      const blockH = HEAD_H + rows * (NODE_H + GY) - GY + IPAD;
      nodesEl.appendChild(zoneColumn(z, g.x, PAD, g.w, blockH, z.key === "state" ? "" : shownOf(n, c[z.key] || n)));
      for (let i = 0; i < n; i++) {
        const col = i % g.cols, row = Math.floor(i / g.cols);
        const nx = g.x + IPAD + col * (g.nodeW + GX), ny = gridTop + row * (NODE_H + GY);
        nodesEl.appendChild(z.key === "state" ? stateCard(items[i], nx, ny, g.nodeW) : memCard(items[i], nx, ny, g.nodeW));
      }
      if (n === 0) {
        const none = document.createElement("div");
        none.className = "mm-none"; none.style.left = (g.x + IPAD) + "px"; none.style.top = gridTop + "px";
        none.style.width = (g.w - IPAD * 2) + "px";
        none.textContent = z.key === "state" ? t("memory.empty_state") : t("memory.no_memories");
        nodesEl.appendChild(none);
      }
      maxBottom = Math.max(maxBottom, PAD + blockH);
    }
    worldH = maxBottom + PAD;
    applyPulses();
    edgesSvg.setAttribute("width", worldW);
    edgesSvg.setAttribute("height", worldH);
    edgesSvg.setAttribute("viewBox", `0 0 ${worldW} ${worldH}`);
  }

  function conceptNode(n, cx, cy, r) {
    const el = document.createElement("div");
    el.className = "mm-cnode";
    el.dataset.concept = n.key;
    el.style.left = (cx - r) + "px"; el.style.top = (cy - r) + "px";
    el.style.width = (2 * r) + "px"; el.style.height = (2 * r) + "px";
    el.title = t("memory.concept_items", { label: n.label, count: n.count });
    const nm = document.createElement("span"); nm.className = "mm-cnname"; nm.textContent = n.label;
    const ct = document.createElement("span"); ct.className = "mm-cncount"; ct.textContent = String(n.count);
    el.append(nm, ct);
    return el;
  }

  function conceptPanel(meta, graph, x, y, w) {
    graph = graph || { nodes: [], links: [] };
    const nodes = graph.nodes || [], links = graph.links || [];
    const contentH = nodes.length ? 440 : 120;
    const panelH = HEAD_H + contentH;
    const b = document.createElement("div");
    b.className = "mm-band k-" + meta.key;
    b.style.left = x + "px"; b.style.top = y + "px"; b.style.width = w + "px"; b.style.height = panelH + "px";
    b.style.borderTopColor = meta.accent;
    const lab = document.createElement("div"); lab.className = "mm-zlabel";
    const head = document.createElement("div"); head.className = "mm-zhead";
    const titleEl = document.createElement("span"); titleEl.className = "mm-ztitle"; titleEl.textContent = t(meta.title);
    head.appendChild(titleEl);
    const c = document.createElement("span"); c.className = "mm-zcount"; c.textContent = shownOf(nodes.length, graph.total || nodes.length); head.appendChild(c);
    const sub = document.createElement("span"); sub.className = "mm-zsub"; sub.textContent = t(meta.sub);
    lab.append(head, sub);
    b.appendChild(lab);
    nodesEl.appendChild(b);
    if (!nodes.length) {
      const none = document.createElement("div");
      none.className = "mm-none"; none.style.left = (x + IPAD) + "px"; none.style.top = (y + HEAD_H) + "px";
      none.style.width = (w - IPAD * 2) + "px";
      none.textContent = t("memory.no_concepts");
      nodesEl.appendChild(none);
      return y + panelH;
    }
    const cx0 = x + w / 2, cy0 = y + HEAD_H + contentH / 2;
    const maxCount = Math.max(1, ...nodes.map((n) => n.count));
    const rOf = (n) => Math.round(24 + 30 * Math.sqrt(n.count / maxCount));
    const R = Math.min(w / 2, contentH / 2) - 78;
    const cpos = {};
    const central = nodes.length >= 5 ? nodes[0] : null;
    const ring = central ? nodes.slice(1) : nodes;
    if (central) cpos[central.key] = { cx: cx0, cy: cy0, r: rOf(central) };
    for (let i = 0; i < ring.length; i++) {
      const ang = (i / ring.length) * Math.PI * 2 - Math.PI / 2;
      cpos[ring[i].key] = { cx: cx0 + Math.cos(ang) * R, cy: cy0 + Math.sin(ang) * R, r: rOf(ring[i]) };
    }
    for (const l of links) {
      const a = cpos[l.a], z = cpos[l.b];
      if (!a || !z) continue;
      const line = document.createElementNS(SVGNS, "path");
      line.setAttribute("d", `M ${a.cx} ${a.cy} L ${z.cx} ${z.cy}`);
      line.setAttribute("class", "mm-cedge");
      line.setAttribute("stroke-width", String(Math.min(6, 0.8 + (l.weight || 1) * 0.7)));
      const ti = document.createElementNS(SVGNS, "title");
      ti.textContent = t("memory.edge_common", { a: l.a, b: l.b, count: l.weight });
      line.appendChild(ti);
      edgesSvg.appendChild(line);
    }
    for (const n of nodes) {
      const p = cpos[n.key];
      nodesEl.appendChild(conceptNode(n, p.cx, p.cy, p.r));
    }
    return y + panelH;
  }

  function renderConcepts(data) {
    const cg = data.concept_graph || {};
    const vw = viewportEl ? viewportEl.getBoundingClientRect().width : 1200;
    worldW = Math.max(720, vw);
    const panelW = worldW - PAD * 2;
    let y = PAD;
    y = conceptPanel({ key: "short", title: "memory.zone_short", sub: "memory.concept_sub_short", accent: "var(--hb-accent2)" }, cg.short, PAD, y, panelW);
    y += COL_GAP;
    y = conceptPanel({ key: "long", title: "memory.zone_long", sub: "memory.concept_sub_long", accent: "var(--hb-accent)" }, cg.long, PAD, y, panelW);
    worldH = y + PAD;
    edgesSvg.setAttribute("width", worldW);
    edgesSvg.setAttribute("height", worldH);
    edgesSvg.setAttribute("viewBox", `0 0 ${worldW} ${worldH}`);
  }

  function render(data) {
    if (!nodesEl || !data) return;
    lastData = data;
    nodesEl.replaceChildren();
    while (edgesSvg.firstChild) edgesSvg.removeChild(edgesSvg.firstChild);
    const c = data.counts || {};
    emptyEl.style.display = (c.total || 0) === 0 ? "block" : "none";
    if (mode === "concepts") renderConcepts(data); else renderSlots(data);
    slotsBtn.classList.toggle("on", mode === "slots");
    conceptsBtn.classList.toggle("on", mode === "concepts");
    const cg = data.concept_graph || {};
    countsEl.textContent = mode === "concepts"
      ? t("memory.counts_concepts", { short: cg.short?.nodes?.length || 0, long: cg.long?.nodes?.length || 0 })
      : t("memory.counts_slots", { short: fmtNum(c.short || 0), long: fmtNum(c.long || 0), concepts: fmtNum(c.concepts || 0) });
  }

  function setMode(m) {
    if (mode === m) return;
    mode = m;
    if (lastData) { render(lastData); fitView(); }
  }

  let expireT = null;
  function applyPulses() {
    if (!nodesEl) return;
    const now = Date.now();
    for (const el of nodesEl.querySelectorAll("[data-mid]")) {
      const p = pulses.get(Number(el.dataset.mid));
      el.classList.remove(...PULSE_CLASSES);
      if (p && p.until > now) el.classList.add(p.cls);
    }
    clearTimeout(expireT);
    if (!pulses.size) return;
    expireT = setTimeout(() => {
      const t0 = Date.now();
      for (const [id, p] of pulses) if (p.until <= t0) pulses.delete(id);
      applyPulses();
    }, 350);
  }

  let inflight = false, again = false;
  async function load() {
    if (inflight) { again = true; return; }
    inflight = true;
    try {
      const data = await api.memoryViewer("cards", { limit: tier.rows });
      if (!data) { countsEl.textContent = t("memory.load_error"); return; }
      render(data);
      if (!fitted) fitView();
    } finally {
      inflight = false;
      if (again) { again = false; load(); }
    }
  }

  let resizeT = null;
  window.addEventListener("resize", () => {
    if (!active || !lastData) return;
    clearTimeout(resizeT);
    resizeT = setTimeout(() => { render(lastData); fitView(); }, 120);
  });

  const clampScale = (s) => Math.max(0.3, Math.min(3, s));
  function onWheel(e) {
    e.preventDefault();
    const r = viewportEl.getBoundingClientRect();
    const lx = e.clientX - r.left, ly = e.clientY - r.top;
    const ns = clampScale(view.scale * (e.deltaY < 0 ? 1.12 : 1 / 1.12));
    const wx = (lx - view.tx) / view.scale, wy = (ly - view.ty) / view.scale;
    view.scale = ns; view.tx = lx - wx * ns; view.ty = ly - wy * ns;
    applyView();
  }
  function onPointerDown(e) {
    if (e.button !== 0) return;
    const sx = e.clientX, sy = e.clientY, tx0 = view.tx, ty0 = view.ty;
    viewportEl.classList.add("panning");
    const move = (ev) => { view.tx = tx0 + (ev.clientX - sx); view.ty = ty0 + (ev.clientY - sy); applyView(); };
    const up = () => { viewportEl.classList.remove("panning"); window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  }
  const zoomBy = (f) => { view.scale = clampScale(view.scale * f); applyView(); };

  const el = h("div", { class: "mv-cards" },
    h("div", { class: "mm-head" },
      h("div", { class: "mm-modes" },
        h("button", { class: "mm-mode on", type: "button", ref: (x) => (slotsBtn = x), title: () => t("memory.view_slots"), onClick: () => setMode("slots") }, () => t("memory.slots_btn")),
        h("button", { class: "mm-mode", type: "button", ref: (x) => (conceptsBtn = x), title: () => t("memory.view_concepts"), onClick: () => setMode("concepts") }, () => t("memory.concepts_btn"))),
      h("span", { class: "mm-counts", ref: (x) => (countsEl = x) }, ""),
      h("div", { class: "mm-tools" },
        h("button", { class: "mm-btn hb-icbtn", type: "button", title: () => t("memory.zoom_out"), onClick: () => zoomBy(1 / 1.2) }, "−"),
        h("button", { class: "mm-btn hb-icbtn", type: "button", title: () => t("memory.zoom_in"), onClick: () => zoomBy(1.2) }, "+"),
        h("button", { class: "mm-btn hb-icbtn", type: "button", title: () => t("memory.fit"), onClick: () => fitView() }, raw(FIT_ICON)),
        h("button", { class: "mm-btn hb-icbtn", type: "button", title: () => t("memory.refresh"), onClick: () => load() }, raw(REFRESH_ICON)))),
    h("div", { class: "mm-viewport", ref: (x) => (viewportEl = x), onWheel, onPointerdown: onPointerDown },
      h("div", { class: "mm-hint" }, () => t("memory.hint")),
      h("div", { class: "mm-empty", ref: (x) => (emptyEl = x) }, () => t("memory.empty_hint")),
      h("div", { class: "mm-world", ref: (x) => (worldEl = x) },
        edgesSvg,
        h("div", { class: "mm-nodes", ref: (x) => (nodesEl = x) }))));

  return {
    el,
    activate() { active = true; fitted = false; load(); },
    deactivate() { active = false; },
    refresh() { if (active) load(); },
    pulse(ev) {
      const cls = OP_CLS[ev?.op] || "pulse-upd";
      const ids = Array.isArray(ev?.ids) ? ev.ids : (ev?.id != null ? [ev.id] : []);
      const until = Date.now() + PULSE_MS;
      for (const id of ids) pulses.set(Number(id), { cls, until });
      if (ids.length && mode === "slots") applyPulses();
    },
  };
}
