// ============================================================================
// MemoryMap — the 🧠 "map of zaelar's memory": a full-screen, VERY visual overlay
// that shows how zaelar's central memory (memory/, V2-002/003) is composed IN REAL
// TIME while you talk. Toggled by the 🧠 icon in the orb bowl (store.memOpen).
//
// TWO VIEWS (toggle in the header — redesign 2026-07-10, at the operator's request):
//
//   · SLOTS     — the memory AS IT IS STORED: three SIDE-BY-SIDE COLUMNS (ESTADO · CORTO ·
//                 LARGO), each a block with a coloured rail; every memory is a card with its
//                 text + scoring + date + metadata (kind, weight, access, pinned). Readable by
//                 ZOOM (wheel) + PAN (drag). This is the literal contents of each storage layer.
//   · CONCEPTOS — the memory AS IT IS ORGANIZED: a CONCEPT MAP (network) — concepts as nodes
//                 (sized by how many data touch them, with the COUNT inside), related to EACH
//                 OTHER by co-occurrence edges. NO content, just the shape of the organization.
//                 CORTO and LARGO are SEPARATE maps (they are separate storages in reality):
//                 the long map uses the persisted concept graph (T126), the short map derives
//                 concepts on the fly. This answers "how is my info connected: salud↔hábitos↔
//                 deporte↔objetivos↔proyectos…" without drilling into any single memory.
//
// REAL-TIME, NO POLLING: the server bridges the bus signal `memory.updated` onto the SSE
// stream (kind:"memory" — see server/__init__.py + services/sse.js), which bumps
// store.memBump(). This component refetches /api/memory/map (debounced) ONLY while open — so
// BOTH views stay live as memory forms. LIVE OBSERVABILITY (V2-014, gated by
// `memory_observability`): in the SLOTS view each SSE pulse tints the affected nodes for a few
// seconds (write=green, overwrite=amber, query=blue) so you SEE the memory forming/being read.
// Theme via --hb-* only.
// ============================================================================
import { h, raw } from "../core/dom.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as api from "../services/api.js?v=2";
import { FIT_ICON, REFRESH_ICON, CLOSE_ICON, PIN_ICON } from "../lib/icons.js?v=1";

const BRAIN = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4.5a3 3 0 0 0-3 3 3 3 0 0 0-1.3 5.7A3 3 0 0 0 8 16.5a3 3 0 0 0 4 2.6"/><path d="M12 4.5a3 3 0 0 1 3 3 3 3 0 0 1 1.3 5.7A3 3 0 0 1 16 16.5a3 3 0 0 1-4 2.6"/><path d="M12 4.5v15"/></svg>`;
const SVGNS = "http://www.w3.org/2000/svg";

// ---- layout constants (px, world-space pre-scale) ----
const PAD = 26, NODE_H = 98, GX = 14, GY = 14;
const NODE_W_MIN = 150;   // target min card width; cards stretch to fill the column width
const IPAD = 14;          // inner padding inside a column block
const HEAD_H = 56;        // column header height (title + count + sub)
const COL_GAP = 34;       // horizontal gap between the three columns

// The three layers, laid out LEFT → RIGHT as columns in the SLOTS view. `frac` = share of the
// usable width (0.10 / 0.20 / 0.70 — the last one is the one that grows). `accent` = top rail.
const ZONES = [
  { key: "state", frac: 0.10, title: "STATE", sub: "awareness of itself and its surroundings", accent: "var(--hb-neutral)" },
  { key: "short", frac: 0.20, title: "SHORT TERM", sub: "recent memory", accent: "var(--hb-accent2)" },
  { key: "long",  frac: 0.70, title: "LONG TERM", sub: "durable facts · preferences · tasks", accent: "var(--hb-accent)" },
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

// State → node descriptors (label + value string). Empty values show as "—" so the near-empty ESTADO is legible.
function stateItems(s) {
  s = s || {};
  const arr = (v) => (Array.isArray(v) && v.length ? v.join(" · ") : "");
  return [
    { label: "mission", val: s.mission },
    { label: "operator", val: s.operator_name },
    { label: "form of address", val: s.treatment },
    { label: "location", val: s.location },
    { label: "language", val: s.language },
    { label: "assistant", val: s.assistant_name },
    { label: "open widgets", val: arr(s.open_widgets) },
    { label: "tasks in progress", val: arr(s.activity) },
    { label: "recent", val: arr(s.recent) },
    { label: "topics", val: arr(s.topics) },
  ];
}

export function MemoryMap() {
  let viewportEl, worldEl, edgesSvg, nodesEl, emptyEl, countsEl, slotsBtn, conceptsBtn;
  let worldH = 400, worldW = 1200;
  let lastData = null;                 // last map payload (for re-render on resize / mode switch)
  let mode = "slots";                  // "slots" | "concepts"
  const pulses = new Map();            // memory id → { cls, until } — live observability tint (SLOTS view)
  const view = { scale: 0.9, tx: PAD, ty: PAD };

  const applyView = () => {
    if (worldEl) worldEl.style.transform = `translate(${view.tx}px,${view.ty}px) scale(${view.scale})`;
  };

  // Default view FILLS THE SCREEN WIDTH (the whole point — use the screen). Height overflows
  // downward → pan/zoom to explore. Never upscale past 1×.
  function fitView() {
    if (!viewportEl) return;
    const r = viewportEl.getBoundingClientRect();
    if (r.width < 20 || r.height < 20) return;
    view.scale = Math.max(0.3, Math.min(r.width / worldW, 1));
    view.tx = Math.max(0, (r.width - worldW * view.scale) / 2);
    view.ty = PAD;
    applyView();
  }

  // ---- node builders (imperative DOM — a live map shouldn't route through reactive bindings) ----
  function memCard(m, x, y, w) {
    const el = document.createElement("div");
    el.className = "mm-node k-" + String(m.kind || "").replace(/[^a-z0-9_]/gi, "");
    if (m.pinned) el.classList.add("pinned");
    if (m.valid === 0) el.classList.add("stale");
    el.dataset.mid = String(m.id);                       // for live-observability tinting by id
    el.style.left = x + "px"; el.style.top = y + "px"; el.style.width = w + "px";
    el.title = `#${m.id} · ${m.kind} · ${m.level}\n${m.text || ""}\n\nscore ${num(m.importance)} · weight ${num(m.weight)} · accesses ${m.access_count || 0}` +
      (m.pinned ? " · 📌" : "") + `\ncreated ${fmtDate(m.created)} · seen ${fmtDate(m.last_access)}` +
      (m.ttl_days != null ? ` · ttl ${m.ttl_days}d` : "");

    const tx = document.createElement("div"); tx.className = "mm-tx"; tx.textContent = m.text || "";
    const meta = document.createElement("div"); meta.className = "mm-meta";
    const chip = (t, cls) => { const c = document.createElement("span"); c.className = "mm-chip" + (cls ? " " + cls : ""); c.textContent = t; return c; };
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
    el.title = it.label + ": " + (empty ? "(empty)" : it.val);
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
    b.style.borderTopColor = z.accent;   // coloured rail per column
    const lab = document.createElement("div"); lab.className = "mm-zlabel";
    const head = document.createElement("div"); head.className = "mm-zhead";
    const t = document.createElement("span"); t.className = "mm-ztitle"; t.textContent = z.title;
    head.appendChild(t);
    if (count !== "") { const c = document.createElement("span"); c.className = "mm-zcount"; c.textContent = count; head.appendChild(c); }
    const sub = document.createElement("span"); sub.className = "mm-zsub"; sub.textContent = z.sub;
    lab.append(head, sub);
    b.appendChild(lab);
    return b;
  }

  // ---- SLOTS view: three storage columns of memory cards ----------------------------------------------------
  function renderSlots(data) {
    const pos = {};
    const vw = viewportEl ? viewportEl.getBoundingClientRect().width : 1200;
    const { geom, worldW: ww } = computeGeom(vw);
    worldW = ww;
    const gridTop = PAD + HEAD_H;
    let maxBottom = PAD;
    for (const z of ZONES) {
      const g = geom[z.key];
      const items = z.key === "state" ? stateItems(data.state) : ((data.layers && data.layers[z.key]) || []);
      const n = items.length;
      const rows = Math.max(1, Math.ceil(n / g.cols));
      const blockH = HEAD_H + rows * (NODE_H + GY) - GY + IPAD;
      nodesEl.appendChild(zoneColumn(z, g.x, PAD, g.w, blockH, z.key === "state" ? "" : n));
      for (let i = 0; i < n; i++) {
        const col = i % g.cols, row = Math.floor(i / g.cols);
        const nx = g.x + IPAD + col * (g.nodeW + GX), ny = gridTop + row * (NODE_H + GY);
        if (z.key === "state") {
          nodesEl.appendChild(stateCard(items[i], nx, ny, g.nodeW));
        } else {
          nodesEl.appendChild(memCard(items[i], nx, ny, g.nodeW));
          pos[items[i].id] = { cx: nx + g.nodeW / 2, cy: ny + NODE_H / 2 };
        }
      }
      if (n === 0) {
        const none = document.createElement("div");
        none.className = "mm-none"; none.style.left = (g.x + IPAD) + "px"; none.style.top = gridTop + "px";
        none.style.width = (g.w - IPAD * 2) + "px";
        none.textContent = z.key === "state" ? "(empty state — it'll fill in as it gets to know you)" : "(no memories in this layer)";
        nodesEl.appendChild(none);
      }
      maxBottom = Math.max(maxBottom, PAD + blockH);
    }
    worldH = maxBottom + PAD;
    applyPulses();
    // (no cross-column edges in the slots view — the graph lives in the CONCEPTOS view)
    edgesSvg.setAttribute("width", worldW);
    edgesSvg.setAttribute("height", worldH);
    edgesSvg.setAttribute("viewBox", `0 0 ${worldW} ${worldH}`);
  }

  // ---- CONCEPTOS view: a concept-network map per storage layer ----------------------------------------------
  // One rounded circular node per concept, sized by `count`, the count printed inside; concept↔concept edges by
  // co-occurrence (weight = shared data). Radial layout: biggest concept in the centre, the rest on a ring.
  function conceptNode(n, cx, cy, r) {
    const el = document.createElement("div");
    el.className = "mm-cnode";
    el.dataset.concept = n.key;
    el.style.left = (cx - r) + "px"; el.style.top = (cy - r) + "px";
    el.style.width = (2 * r) + "px"; el.style.height = (2 * r) + "px";
    el.title = `${n.label} — ${n.count} item(s)`;
    const nm = document.createElement("span"); nm.className = "mm-cnname"; nm.textContent = n.label;
    const ct = document.createElement("span"); ct.className = "mm-cncount"; ct.textContent = String(n.count);
    el.append(nm, ct);
    return el;
  }

  // Draws one titled concept-map panel and returns its bottom Y. `graph` = {nodes:[{key,label,count}], links}.
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
    const t = document.createElement("span"); t.className = "mm-ztitle"; t.textContent = meta.title;
    head.appendChild(t);
    const c = document.createElement("span"); c.className = "mm-zcount"; c.textContent = nodes.length; head.appendChild(c);
    const sub = document.createElement("span"); sub.className = "mm-zsub"; sub.textContent = meta.sub;
    lab.append(head, sub);
    b.appendChild(lab);
    nodesEl.appendChild(b);

    if (!nodes.length) {
      const none = document.createElement("div");
      none.className = "mm-none"; none.style.left = (x + IPAD) + "px"; none.style.top = (y + HEAD_H) + "px";
      none.style.width = (w - IPAD * 2) + "px";
      none.textContent = "(no concepts in this layer yet)";
      nodesEl.appendChild(none);
      return y + panelH;
    }

    const cx0 = x + w / 2, cy0 = y + HEAD_H + contentH / 2;
    const maxCount = Math.max(1, ...nodes.map((n) => n.count));
    const rOf = (n) => Math.round(24 + 30 * Math.sqrt(n.count / maxCount));   // node radius by count
    const R = Math.min(w / 2, contentH / 2) - 78;                            // ring radius (leave room for nodes)
    const cpos = {};

    // centre = biggest concept when there are enough to form a hub; ring = the rest.
    const central = nodes.length >= 5 ? nodes[0] : null;
    const ring = central ? nodes.slice(1) : nodes;
    if (central) cpos[central.key] = { cx: cx0, cy: cy0, r: rOf(central) };
    for (let i = 0; i < ring.length; i++) {
      const ang = (i / ring.length) * Math.PI * 2 - Math.PI / 2;
      cpos[ring[i].key] = { cx: cx0 + Math.cos(ang) * R, cy: cy0 + Math.sin(ang) * R, r: rOf(ring[i]) };
    }

    // links FIRST (under the nodes), into the shared SVG.
    for (const l of links) {
      const a = cpos[l.a], z = cpos[l.b];
      if (!a || !z) continue;
      const line = document.createElementNS(SVGNS, "path");
      line.setAttribute("d", `M ${a.cx} ${a.cy} L ${z.cx} ${z.cy}`);
      line.setAttribute("class", "mm-cedge");
      line.setAttribute("stroke-width", String(Math.min(6, 0.8 + (l.weight || 1) * 0.7)));
      const ti = document.createElementNS(SVGNS, "title");
      ti.textContent = `${l.a} ↔ ${l.b} · ${l.weight} item(s) in common`;
      line.appendChild(ti);
      edgesSvg.appendChild(line);
    }
    // nodes on top.
    for (const n of nodes) {
      const p = cpos[n.key];
      nodesEl.appendChild(conceptNode(n, p.cx, p.cy, p.r));
    }
    return y + panelH;
  }

  function renderConcepts(data) {
    const cg = data.concept_graph || { short: { nodes: [], links: [] }, long: { nodes: [], links: [] } };
    const vw = viewportEl ? viewportEl.getBoundingClientRect().width : 1200;
    worldW = Math.max(720, vw);
    const panelW = worldW - PAD * 2;
    let y = PAD;
    y = conceptPanel({ key: "short", title: "SHORT TERM", sub: "concept map of recent memory", accent: "var(--hb-accent2)" }, cg.short, PAD, y, panelW);
    y += COL_GAP;
    y = conceptPanel({ key: "long", title: "LONG TERM", sub: "concept map of durable facts", accent: "var(--hb-accent)" }, cg.long, PAD, y, panelW);
    worldH = y + PAD;
    edgesSvg.setAttribute("width", worldW);
    edgesSvg.setAttribute("height", worldH);
    edgesSvg.setAttribute("viewBox", `0 0 ${worldW} ${worldH}`);
  }

  function render(data) {
    if (!nodesEl) return;
    lastData = data;
    nodesEl.replaceChildren();
    while (edgesSvg.firstChild) edgesSvg.removeChild(edgesSvg.firstChild);

    const total = (data.counts && data.counts.total) || 0;
    if (emptyEl) emptyEl.style.display = total === 0 ? "block" : "none";

    if (mode === "concepts") renderConcepts(data);
    else renderSlots(data);

    if (slotsBtn) slotsBtn.classList.toggle("on", mode === "slots");
    if (conceptsBtn) conceptsBtn.classList.toggle("on", mode === "concepts");

    if (countsEl) {
      const c = data.counts || {};
      const cg = data.concept_graph || {};
      const cn = (cg.short?.nodes?.length || 0) + (cg.long?.nodes?.length || 0);
      countsEl.textContent = mode === "concepts"
        ? `${cg.short?.nodes?.length || 0} short concepts · ${cg.long?.nodes?.length || 0} long concepts`
        : `${c.short || 0} short · ${c.long || 0} long · ${cn} concepts`;
    }
  }

  function setMode(m) {
    if (mode === m) return;
    mode = m;
    if (lastData) { render(lastData); fitView(); }
  }

  // ---- live observability: tint nodes by id for a few seconds (write=green, overwrite=amber, query=blue) ----
  const PULSE_MS = 4200;
  const OP_CLS = {
    write: "pulse-new", episode: "pulse-new",
    reinforce: "pulse-upd", state: "pulse-upd", consolidate: "pulse-upd", link: "pulse-upd",
    migrate_inbox: "pulse-upd", pin: "pulse-upd", unpin: "pulse-upd",
    query: "pulse-qry",
  };
  const PULSE_CLASSES = ["pulse-new", "pulse-upd", "pulse-qry"];
  let expireT = null;

  function applyPulses() {
    if (!nodesEl) return;
    const now = Date.now();
    for (const el of nodesEl.querySelectorAll("[data-mid]")) {
      const id = Number(el.dataset.mid);
      const p = pulses.get(id);
      el.classList.remove(...PULSE_CLASSES);
      if (p && p.until > now) el.classList.add(p.cls);
    }
    scheduleExpire();
  }
  function scheduleExpire() {
    clearTimeout(expireT);
    if (!pulses.size) return;
    expireT = setTimeout(() => {
      const now = Date.now();
      for (const [id, p] of pulses) if (p.until <= now) pulses.delete(id);
      applyPulses();
    }, 350);
  }
  function pulse(ev) {
    if (!ev || !store.memOpen()) return;
    const cls = OP_CLS[ev.op] || "pulse-upd";
    const ids = Array.isArray(ev.ids) ? ev.ids : (ev.id != null ? [ev.id] : []);
    const until = Date.now() + PULSE_MS;
    for (const id of ids) pulses.set(Number(id), { cls, until });
    if (ids.length && mode === "slots") applyPulses();
  }

  // ---- data load (debounced; refetch on open + on every memory.updated while open) ----
  let inflight = false, again = false, debounceT = null, firstFit = false;
  async function load(fit) {
    if (inflight) { again = true; return; }
    inflight = true;
    try {
      const data = await api.getMemoryMap();
      render(data);
      if (fit || !firstFit) { firstFit = true; fitView(); }
    } finally {
      inflight = false;
      if (again) { again = false; scheduleLoad(); }
    }
  }
  function scheduleLoad() {
    clearTimeout(debounceT);
    debounceT = setTimeout(() => load(false), 250);
  }

  createEffect(() => {
    const open = store.memOpen();
    const bump = store.memBump();
    void bump;
    if (!open) { firstFit = false; pulses.clear(); return; }
    scheduleLoad();
  });

  createEffect(() => {
    const p = store.memPulse();
    if (p) pulse(p);
  });

  let resizeT = null;
  const onResize = () => {
    if (!store.memOpen() || !lastData) return;
    clearTimeout(resizeT);
    resizeT = setTimeout(() => { render(lastData); fitView(); }, 120);
  };
  window.addEventListener("resize", onResize);

  // ---- zoom (wheel, around cursor) + pan (drag background) + controls ----
  const clampScale = (s) => Math.max(0.3, Math.min(3, s));
  function onWheel(e) {
    e.preventDefault();
    const r = viewportEl.getBoundingClientRect();
    const lx = e.clientX - r.left, ly = e.clientY - r.top;
    const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    const ns = clampScale(view.scale * factor);
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

  const close = () => store.setMemOpen(false);
  const onKey = (e) => { if (e.key === "Escape" && store.memOpen()) close(); };
  window.addEventListener("keydown", onKey);

  edgesSvg = document.createElementNS(SVGNS, "svg");
  edgesSvg.setAttribute("class", "mm-edges");

  return h("div", { class: () => "memmap" + (store.memOpen() ? " open" : "") },
    h("div", { class: "mm-head" },
      h("span", { class: "mm-brand" }, raw(BRAIN), h("b", {}, "Memory map")),
      h("div", { class: "mm-modes" },
        h("button", { class: "mm-mode on", ref: (el) => (slotsBtn = el), title: "View memory as it's stored (state · short · long)", onClick: () => setMode("slots") }, "Slots"),
        h("button", { class: "mm-mode", ref: (el) => (conceptsBtn = el), title: "View the concept map: how the information is organized and connected", onClick: () => setMode("concepts") }, "Concepts"),
      ),
      h("span", { class: "mm-counts", ref: (el) => (countsEl = el) }, ""),
      h("div", { class: "mm-tools" },
        h("button", { class: "mm-btn hb-icbtn", title: "Zoom out", onClick: () => zoomBy(1 / 1.2) }, "−"),
        h("button", { class: "mm-btn hb-icbtn", title: "Zoom in", onClick: () => zoomBy(1.2) }, "+"),
        h("button", { class: "mm-btn hb-icbtn", title: "Fit to view", onClick: () => fitView() }, raw(FIT_ICON)),
        h("button", { class: "mm-btn hb-icbtn", title: "Refresh", onClick: () => load(false) }, raw(REFRESH_ICON)),
        h("button", { class: "mm-btn mm-close hb-icbtn", title: "Close (Esc)", onClick: close }, raw(CLOSE_ICON)),
      ),
    ),
    h("div", { class: "mm-viewport", ref: (el) => (viewportEl = el), onWheel, onPointerdown: onPointerDown },
      h("div", { class: "mm-hint" }, "wheel = zoom · drag = pan · Slots = content · Concepts = organization"),
      h("div", { class: "mm-empty", ref: (el) => (emptyEl = el) }, "Memory is still empty. Talk to zaelar and you'll watch it fill in here live."),
      h("div", { class: "mm-world", ref: (el) => (worldEl = el) },
        edgesSvg,
        h("div", { class: "mm-nodes", ref: (el) => (nodesEl = el) }),
      ),
    ),
  );
}
