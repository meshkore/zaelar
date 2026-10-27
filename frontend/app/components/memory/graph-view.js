// ============================================================================
// memory/graph-view.js — the «Graph» tab of the memory viewer (V2-808, V2-814).
//
// It shows how the memory RELATES things — concepts and the weight between them — never what is stored: the
// server sends the concepts of a time window with their counts, the concept↔concept weights, and as many memory
// dots as the device's node budget allows (`/api/memory/viewer/graph`); a selected concept is its numbers and the
// concepts it is related to (`/api/memory/viewer/concept`), with no memory text. The map is his own memory only:
// inbound messages are not in it.
//
// Drawing: ONE <canvas>, sized to its section in device pixels and re-fitted when the section resizes — the
// previous map was absolutely positioned DOM in a world scaled once at open time, which is how the concept maps
// ended up pushed into the bottom-right corner. Level of detail: memory dots are skipped while they would be
// sub-pixel, labels only appear for the biggest concepts or once a node is large enough on screen. The layout
// runs in a Worker (`force-worker.js`) and stops when it settles; the canvas repaints only while something moves.
//
// The look (V2-815, for sharing): a night-sky canvas, concepts coloured by the COMMUNITY they form (label
// propagation over the concept links, so related concepts share a hue), glowing hubs, edges that blend the two
// colours they join, memories as small stars. While every concept AND memory of the window fits the device's
// node budget, all of them are drawn; past it the server sends only the top level (the concepts) and the
// toolbar says so. «Image» saves the current view as a PNG.
// ============================================================================
import { h } from "../../core/dom.js?v=2";
import * as store from "../../core/store.js?v=2";
import * as api from "../../services/api.js?v=2";
import { t } from "../../core/i18n.js?v=1";
import { num, ago } from "./format.js?v=2";

const PALETTE = ["--hb-accent", "--hb-accent2", "--hb-warn", "--hb-ok", "--hb-risk", "--hb-muted"];
const PERIODS = [{ days: 1, key: "memory.period_1" }, { days: 7, key: "memory.period_7" },
                 { days: 30, key: "memory.period_30" }, { days: 0, key: "memory.period_all" }];
const FIT_PAD = 28, FIT_FOOT = 44;

// The view transform that puts a bounding box in the MIDDLE of a W×H panel, scaled to fill it (never past 2×).
// Exported: the rendered test reads it, and its disarm replaces it.
// `foot` is the band the legend covers at the bottom: the drawing is centred in what is left above it.
export function fitTransform(box, W, H, pad = FIT_PAD, foot = FIT_FOOT) {
  const bw = Math.max(1, box.x1 - box.x0), bh = Math.max(1, box.y1 - box.y0);
  const k = Math.min(2, Math.max(0.05, Math.min((W - 2 * pad) / bw, (H - 2 * pad - foot) / bh)));
  H -= foot;
  return { k, tx: W / 2 - ((box.x0 + box.x1) / 2) * k, ty: H / 2 - ((box.y0 + box.y1) / 2) * k };
}

const cap = (s) => (s ? s.charAt(0).toLocaleUpperCase(store.lang() || "en") + s.slice(1) : "");

export function GraphView({ tier }) {
  const st = {
    days: 0, layers: new Set(["short", "long"]), data: null,
    nodes: [], drawLinks: [], pos: null, view: { k: 1, tx: 0, ty: 0 }, autoFit: true,
    selected: "", hover: -1, labels: true, hues: null, timeline: [], brushFrom: -1, settled: true, pulses: new Map(),
  };
  let canvas, section, aside, footer, showingEl, chipsEl, periodEl, bars, brushBox, worker, raf = 0, colors = [];
  let active = false;

  // ── data ──────────────────────────────────────────────────────────────────────────────────────────────
  const params = () => ({ days: st.days, layers: [...st.layers].join(","),
                          lanes: "own", budget: tier.nodes });

  async function load(warm = false) {
    const data = await api.memoryViewer("graph", params());
    if (!data) { section.dataset.state = "error"; paintEmpty(t("memory.load_error")); return; }
    const prev = new Map();
    if (warm && st.pos) st.nodes.forEach((n, i) => prev.set(n.id, [st.pos[2 * i], st.pos[2 * i + 1]]));
    st.data = data;
    build(prev);
    renderChrome();
    if (st.selected && !data.concepts.some((c) => c.key === st.selected)) select("");
    else if (!st.selected && data.concepts.length) select(data.concepts[0].key);
  }

  function build(prev) {
    const d = st.data;
    const maxC = Math.max(1, ...d.concepts.map((c) => c.count));
    const idx = new Map();
    const nodes = [];
    d.concepts.forEach((c, i) => {
      idx.set(c.key, nodes.length);
      nodes.push({ id: "c:" + c.key, hub: true, key: c.key, label: cap(c.label), count: c.count, rank: i,
                   r: 10 + 26 * Math.sqrt(c.count / maxC), color: i % PALETTE.length });
    });
    const links = [], drawLinks = [];
    const maxW = Math.max(1, ...d.links.map((l) => l.w));
    for (const l of d.links) {
      const s = idx.get(l.a), e = idx.get(l.b);
      if (s == null || e == null) continue;
      links.push({ s, t: e, len: 190 - Math.min(80, l.w * 8), k: 0.015 + 0.04 * (l.w / maxW) });
      drawLinks.push({ s, t: e, w: 0.8 + 2.6 * Math.sqrt(l.w / maxW), hub: true });
    }
    for (const m of d.memories) {
      const home = idx.get(m.c[0]);
      if (home == null) continue;
      const i = nodes.length;
      nodes.push({ id: "m:" + m.id, mid: m.id, hub: false, key: m.c[0], r: 2.6 + 3 * Math.min(1, m.w || 0),
                   color: nodes[home].color, level: m.level });
      links.push({ s: home, t: i, len: nodes[home].r + 26, k: 0.12 });
      drawLinks.push({ s: home, t: i, w: 0.6, hub: false });
      for (const c of m.c.slice(1)) {
        const o = idx.get(c);
        if (o != null) links.push({ s: o, t: i, len: 140, k: 0.004 });
      }
    }
    communities(nodes, d.links, idx);
    st.nodes = nodes; st.drawLinks = drawLinks;
    st.pos = new Float32Array(nodes.length * 2);
    const seeds = nodes.map((n) => { const p = prev.get(n.id); return { r: n.r, hub: n.hub, x: p?.[0], y: p?.[1] }; });
    nodes.forEach((n, i) => { const p = prev.get(n.id); if (p) { st.pos[2 * i] = p[0]; st.pos[2 * i + 1] = p[1]; } });
    section.dataset.nodes = String(nodes.length);
    if (!nodes.length) { stopWorker(); paintEmpty(t("memory.graph_empty")); return; }
    section.dataset.state = "running";
    st.settled = false;
    startWorker({ nodes: seeds, links });
  }

  // Label propagation over the concept links: a concept takes the community its links weigh most towards.
  function communities(nodes, links, idx) {
    const hubs = nodes.filter((n) => n.hub);
    const lab = hubs.map((_, i) => i);
    const adj = hubs.map(() => []);
    for (const l of links) {
      const a = idx.get(l.a), b = idx.get(l.b);
      if (a == null || b == null) continue;
      adj[a].push([b, l.w]); adj[b].push([a, l.w]);
    }
    for (let it = 0; it < 10; it++) {
      let moved = false;
      for (let i = 0; i < hubs.length; i++) {
        const score = new Map();
        for (const [j, w] of adj[i]) score.set(lab[j], (score.get(lab[j]) || 0) + w);
        let best = lab[i], bw = score.get(lab[i]) || 0;
        for (const [l, w] of score) if (w > bw || (w === bw && l < best)) { best = l; bw = w; }
        if (best !== lab[i]) { lab[i] = best; moved = true; }
      }
      if (!moved) break;
    }
    // One hue per concept, spread by the golden angle; inside a small community the hues stay close, so related
    // concepts read as one family. One community spanning everything (a dense memory) would paint it all one
    // colour: past a third of the concepts a community does not pull hues at all.
    const members = new Map();
    for (let i = 0; i < hubs.length; i++) members.set(lab[i], [...(members.get(lab[i]) || []), i]);
    const base = new Map([...members.keys()].map((l, i) => [l, (200 + i * 137.508) % 360]));
    st.hues = hubs.map((_, i) => {
      const group = members.get(lab[i]);
      if (group.length > Math.max(3, hubs.length / 3)) return (200 + i * 137.508) % 360;
      return (base.get(lab[i]) + group.indexOf(i) * 18) % 360;
    });
    nodes.forEach((n, i) => { n.color = n.hub ? i : nodes[idx.get(n.key)].color; });
  }
  const hsl = (h, l = 62, a = 1) => `hsla(${h.toFixed(0)},88%,${l}%,${a})`;

  function startWorker(payload) {
    if (!worker) {
      worker = new Worker(new URL("./force-worker.js", import.meta.url));
      worker.onmessage = (ev) => {
        const m = ev.data || {};
        if (!m.pos || m.pos.length !== st.nodes.length * 2) return;   // a reply to a graph we replaced
        st.pos = m.pos;
        if (m.type === "settled") { st.settled = true; section.dataset.state = "settled"; }
        if (st.autoFit) fit();
        schedule();
      };
    }
    worker.postMessage(payload);
  }
  function stopWorker() { if (worker) { worker.terminate(); worker = null; } }

  // ── view ──────────────────────────────────────────────────────────────────────────────────────────────
  function bbox() {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    st.nodes.forEach((n, i) => {
      const x = st.pos[2 * i], y = st.pos[2 * i + 1], r = n.r + (n.hub ? 22 : 0);
      x0 = Math.min(x0, x - r); y0 = Math.min(y0, y - r); x1 = Math.max(x1, x + r); y1 = Math.max(y1, y + r);
    });
    return { x0, y0, x1, y1 };
  }
  function fit() {
    if (!st.nodes.length || !canvas) return;
    const W = canvas.clientWidth, H = canvas.clientHeight;
    if (W < 10 || H < 10) return;
    st.view = fitTransform(bbox(), W, H);
  }
  function resize() {
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const W = section.clientWidth, H = section.clientHeight;
    canvas.width = Math.max(1, Math.round(W * dpr)); canvas.height = Math.max(1, Math.round(H * dpr));
    canvas.style.width = W + "px"; canvas.style.height = H + "px";
    if (st.autoFit) fit();
    schedule();
  }
  function schedule() { if (!raf) raf = requestAnimationFrame(() => { raf = 0; draw(); }); }

  function readColors() {
    const cs = getComputedStyle(section);
    colors = PALETTE.map((v) => cs.getPropertyValue(v).trim() || "#999");
  }
  const SKY = { top: "#0d1224", bottom: "#05070d", ink: "#eef2ff", halo: "rgba(5,7,13,.85)" };

  // The night sky behind the graph, for the saved image only: on screen the panel paints the same sky in CSS
  // (memory-viewer.css), so a frame never repaints thousands of stars. Seeded: the same field every time.
  function sky(c, W, H) {
    const g = c.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, SKY.top); g.addColorStop(1, SKY.bottom);
    c.fillStyle = g; c.fillRect(0, 0, W, H);
    const v = c.createRadialGradient(W / 2, H / 2, Math.min(W, H) * 0.1, W / 2, H / 2, Math.max(W, H) * 0.7);
    v.addColorStop(0, "rgba(90,110,255,.10)"); v.addColorStop(1, "rgba(0,0,0,0)");
    c.fillStyle = v; c.fillRect(0, 0, W, H);
    let seed = 7;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    c.fillStyle = "#ffffff";
    for (let i = 0; i < Math.round((W * H) / 2600); i++) {
      c.globalAlpha = 0.08 + rnd() * 0.25;
      c.fillRect(rnd() * W, rnd() * H, rnd() < 0.9 ? 1 : 1.6, rnd() < 0.9 ? 1 : 1.6);
    }
    c.globalAlpha = 1;
  }

  function draw(target, scale = 1) {
    const cv = target || canvas;
    if (!cv || !st.pos) return;
    const c = cv.getContext("2d");
    const dpr = target ? scale : (window.devicePixelRatio || 1);
    readColors();
    const font = getComputedStyle(section).fontFamily;
    const W = canvas.clientWidth, H = canvas.clientHeight;
    const always = W < 600 ? 8 : 40;   // labels shown at any zoom: fewer on a phone
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, W, H);
    if (target) sky(c, W, H);
    const { k, tx, ty } = st.view;
    c.setTransform(dpr * k, 0, 0, dpr * k, dpr * tx, dpr * ty);
    const P = st.pos, N = st.nodes, hue = (n) => st.hues?.[n.color] ?? 210;
    const now = performance.now();
    c.globalCompositeOperation = "lighter";
    // edges: a curve whose colour runs from one concept's hue to the other's
    for (const l of st.drawLinks) {
      const a = N[l.s], b = N[l.t];
      const ax = P[2 * l.s], ay = P[2 * l.s + 1], bx = P[2 * l.t], by = P[2 * l.t + 1];
      const sel = st.selected && (a.key === st.selected || (l.hub && b.key === st.selected));
      if (l.hub) {
        const g = c.createLinearGradient(ax, ay, bx, by);
        const al = sel ? 0.9 : (st.selected ? 0.18 : 0.45);
        g.addColorStop(0, hsl(hue(a), 62, al)); g.addColorStop(1, hsl(hue(b), 62, al));
        c.strokeStyle = g;
        c.lineWidth = l.w * (sel ? 1.6 : 1) / Math.max(0.6, k);
      } else {
        c.strokeStyle = hsl(hue(a), 70, st.selected && a.key !== st.selected ? 0.05 : 0.16);
        c.lineWidth = l.w / Math.max(0.6, k);
      }
      c.beginPath();
      c.moveTo(ax, ay);
      if (l.hub) {                                 // a gentle curve: the bend is perpendicular to the chord
        const mx = (ax + bx) / 2, my = (ay + by) / 2, dx = bx - ax, dy = by - ay;
        c.quadraticCurveTo(mx - dy * 0.12, my + dx * 0.12, bx, by);
      } else c.lineTo(bx, by);
      c.stroke();
    }
    // memories: small stars — a dot plus a faint glow once they are big enough on screen
    const px = 1.2 / k;
    for (let i = 0; i < N.length; i++) {
      const n = N[i];
      if (n.hub) continue;
      const x = P[2 * i], y = P[2 * i + 1], hh = hue(n);
      const dim = st.selected && n.key !== st.selected ? 0.35 : 1;
      if (n.r * k >= 2.5) {
        c.fillStyle = hsl(hh, 65, 0.16 * dim);
        c.beginPath(); c.arc(x, y, n.r * 2.6, 0, Math.PI * 2); c.fill();
      }
      c.fillStyle = hsl(hh, n.level === "short" ? 82 : 70, 0.9 * dim);
      if (n.r < px) c.fillRect(x - px / 2, y - px / 2, px, px);
      else { c.beginPath(); c.arc(x, y, n.r, 0, Math.PI * 2); c.fill(); }
      const p = st.pulses.get(n.mid);
      if (p && p > now) {
        c.strokeStyle = SKY.ink; c.lineWidth = 1.5 / k;
        c.beginPath(); c.arc(x, y, n.r + 4 / k, 0, Math.PI * 2); c.stroke();
      }
    }
    // concepts: a wide halo, then a bright core
    for (let i = 0; i < N.length; i++) {
      const n = N[i];
      if (!n.hub) continue;
      const x = P[2 * i], y = P[2 * i + 1], hh = hue(n);
      const sel = n.key === st.selected;
      const dim = st.selected && !sel ? 0.55 : 1;
      const R = n.r * (sel ? 4.2 : 3.2);
      const g = c.createRadialGradient(x, y, 0, x, y, R);
      g.addColorStop(0, hsl(hh, 60, 0.55 * dim)); g.addColorStop(0.35, hsl(hh, 55, 0.18 * dim)); g.addColorStop(1, hsl(hh, 50, 0));
      c.fillStyle = g; c.beginPath(); c.arc(x, y, R, 0, Math.PI * 2); c.fill();
    }
    c.globalCompositeOperation = "source-over";
    for (let i = 0; i < N.length; i++) {
      const n = N[i];
      if (!n.hub) continue;
      const x = P[2 * i], y = P[2 * i + 1], hh = hue(n);
      const sel = n.key === st.selected;
      const core = c.createRadialGradient(x - n.r * 0.3, y - n.r * 0.3, n.r * 0.1, x, y, n.r);
      core.addColorStop(0, hsl(hh, 92)); core.addColorStop(1, hsl(hh, 52));
      c.fillStyle = core;
      c.beginPath(); c.arc(x, y, n.r, 0, Math.PI * 2); c.fill();
      if (sel) {
        c.strokeStyle = hsl(hh, 80); c.lineWidth = 2 / k;
        c.beginPath(); c.arc(x, y, n.r + 7 / k, 0, Math.PI * 2); c.stroke();
      }
    }
    // labels — the biggest few always, the rest once they are big enough on screen
    if (st.labels) {
      for (let i = 0; i < N.length; i++) {
        const n = N[i];
        if (!n.hub) continue;
        const sel = n.key === st.selected;
        if (!(n.rank < always || n.r * k >= 12 || sel || i === st.hover)) continue;
        const x = P[2 * i], y = P[2 * i + 1];
        c.font = `${sel || n.rank < 3 ? 700 : 600} ${(n.rank < 3 ? 15 : 13) / k}px ${font}`;
        c.textAlign = "center"; c.textBaseline = "top";
        const text = `${n.label} · ${num(n.count)}`;
        c.strokeStyle = SKY.halo; c.lineWidth = 4 / k; c.lineJoin = "round";
        c.strokeText(text, x, y + n.r + 6 / k);
        c.fillStyle = sel ? hsl(hue(n), 85) : SKY.ink;
        c.fillText(text, x, y + n.r + 6 / k);
      }
    }
    if (target) return;
    if ([...st.pulses.values()].some((u) => u > now)) schedule();
  }

  // «Image»: the current view at 2× on an off-screen canvas, with a small signature, saved as a PNG.
  function exportPng() {
    if (!st.nodes.length) return;
    const W = canvas.clientWidth, H = canvas.clientHeight, S = 2;
    const off = document.createElement("canvas");
    off.width = W * S; off.height = H * S;
    draw(off, S);
    const c = off.getContext("2d");
    c.setTransform(S, 0, 0, S, 0, 0);
    c.font = `600 13px ${getComputedStyle(section).fontFamily}`;
    c.textAlign = "right"; c.textBaseline = "bottom"; c.fillStyle = "rgba(238,242,255,.55)";
    c.fillText(t("memory.export_signature", { n: num(st.data?.total?.concepts || 0) }), W - 16, H - 12);
    off.toBlob((b) => {
      if (!b) return;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(b);
      a.download = `zaelar-memory-${new Date().toISOString().slice(0, 10)}.png`;
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    }, "image/png");
  }

  function paintEmpty(msg) {
    if (!canvas) return;
    st.nodes = []; st.pos = new Float32Array(0); st.drawLinks = [];
    const c = canvas.getContext("2d");
    c.setTransform(1, 0, 0, 1, 0, 0); c.clearRect(0, 0, canvas.width, canvas.height);
    emptyEl.textContent = msg; emptyEl.hidden = false;
    renderChrome();
  }

  // ── interaction ───────────────────────────────────────────────────────────────────────────────────────
  function at(ev) {
    const r = canvas.getBoundingClientRect();
    const { k, tx, ty } = st.view;
    const wx = (ev.clientX - r.left - tx) / k, wy = (ev.clientY - r.top - ty) / k;
    let best = -1, bd = Infinity;
    st.nodes.forEach((n, i) => {
      const dx = st.pos[2 * i] - wx, dy = st.pos[2 * i + 1] - wy, d = Math.sqrt(dx * dx + dy * dy);
      const reach = n.r + 6 / k;
      if (d <= reach && (d < bd || (n.hub && best >= 0 && !st.nodes[best].hub))) { best = i; bd = d; }
    });
    return best;
  }
  function onWheel(e) {
    e.preventDefault();
    zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - canvas.getBoundingClientRect().left,
           e.clientY - canvas.getBoundingClientRect().top);
  }
  function zoomAt(f, lx, ly) {
    const v = st.view, nk = Math.max(0.05, Math.min(8, v.k * f));
    const wx = (lx - v.tx) / v.k, wy = (ly - v.ty) / v.k;
    st.view = { k: nk, tx: lx - wx * nk, ty: ly - wy * nk };
    st.autoFit = false; schedule();
  }
  function onDown(e) {
    if (e.button !== 0) return;
    const sx = e.clientX, sy = e.clientY, v0 = { ...st.view };
    let moved = false;
    const move = (ev) => {
      if (Math.abs(ev.clientX - sx) + Math.abs(ev.clientY - sy) > 3) moved = true;
      if (!moved) return;
      st.view = { k: v0.k, tx: v0.tx + ev.clientX - sx, ty: v0.ty + ev.clientY - sy };
      st.autoFit = false; schedule();
    };
    const up = (ev) => {
      window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
      if (!moved) { const i = at(ev); if (i >= 0) select(st.nodes[i].key); }
    };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  }
  function onMove(e) {
    const i = at(e);
    if (i !== st.hover) { st.hover = i; canvas.style.cursor = i >= 0 ? "pointer" : "grab"; schedule(); }
  }

  // ── the detail panel: the concept and what it is related to ─────────────────────────────────────────────
  let detailHead, detailList;
  async function select(key) {
    st.selected = key; schedule();
    detailList.replaceChildren();
    if (!key) { detailHead.replaceChildren(h("p", { class: "mv-muted" }, t("memory.detail_empty"))); return; }
    const p = await api.memoryViewer("concept", conceptParams(key));
    if (!p || key !== st.selected) return;
    const colorOf = (k) => {
      const i = st.nodes.findIndex((n) => n.hub && n.key === k);
      return i >= 0 && st.hues ? hsl(st.hues[i], 50) : "var(--hb-accent)";
    };
    detailHead.replaceChildren(
      h("p", { class: "hb-sectitle" }, t("memory.detail_kicker")),
      h("h2", { class: "mv-detail-title", style: { color: colorOf(key) } }, cap(p.label)),
      h("p", { class: "mv-muted" }, t("memory.detail_line", { count: num(p.count), ago: ago(p.last) })));
    if (!p.related.length) { detailList.append(h("li", { class: "mv-muted" }, t("memory.related_none"))); return; }
    const top = Math.max(1, ...p.related.map((r) => r.count));
    detailList.append(h("li", { class: "hb-sectitle mv-related-title" }, t("memory.related_title")),
      ...p.related.map((r) => h("li", {},
        h("button", { class: "mv-related", type: "button", onClick: () => select(r.key),
                      style: { "--mv-accent": colorOf(r.key) } },
          h("span", { class: "mv-related-name" }, cap(r.key)),
          h("span", { class: "mv-related-n" }, t("memory.related_shared", { n: num(r.count) })),
          h("span", { class: "mv-fill" }, h("i", { style: { width: Math.max(6, (r.count / top) * 100) + "%" } }))))));
  }
  const conceptParams = (key) => ({ key, days: st.days, layers: [...st.layers].join(","), lanes: "own" });

  // ── chrome: filters, counters, the time brush ─────────────────────────────────────────────────────────
  let emptyEl;
  function renderChrome() {
    const d = st.data;
    periodEl.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed",
      String(st.brushFrom < 0 && Number(b.dataset.days) === st.days)));
    const lc = d?.layer_counts || { short: 0, long: 0, messages: 0 };
    chipsEl.replaceChildren(
      chip("short", t("memory.layer_short", { n: num(lc.short) }), st.layers.has("short"), () => toggleLayer("short")),
      chip("long", t("memory.layer_long", { n: num(lc.long) }), st.layers.has("long"), () => toggleLayer("long")),
    );
    showingEl.textContent = !d ? "" : d.collapsed
      ? t("memory.showing_top", { n: num(d.concepts.length), total: num(d.total?.nodes || 0) })
      : t("memory.showing_all", { n: num(d.concepts.length), m: num(d.memories.length) });
    if (emptyEl && st.nodes.length) emptyEl.hidden = true;
  }
  const chip = (kind, text, on, fn) => h("button", { class: `mv-layer mv-layer--${kind}`, type: "button",
                                                    "aria-pressed": String(on), onClick: fn }, text);
  function toggleLayer(l) {
    if (st.layers.has(l) && st.layers.size === 1) return;   // one layer always stays on
    st.layers.has(l) ? st.layers.delete(l) : st.layers.add(l);
    load();
  }
  function setPeriod(days) { st.days = days; st.brushFrom = -1; st.autoFit = true; load(); loadTimeline(); }

  async function loadTimeline() {
    const span = st.days === 0 ? 90 : Math.max(14, st.days);
    const tl = await api.memoryViewer("timeline", { days: span });
    const byDay = new Map((tl?.days || []).map((r) => [r.day, r.own]));
    const out = [];
    for (let i = span - 1; i >= 0; i--) {
      const d = new Date(Date.now() - i * 86400000);
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      out.push({ day: key, n: byDay.get(key) || 0 });
    }
    st.timeline = out;
    paintBrush();
  }
  function paintBrush() {
    const max = Math.max(1, ...st.timeline.map((b) => b.n));
    const span = st.timeline.length;
    const from = st.brushFrom >= 0 ? st.brushFrom : (st.days ? Math.max(0, span - st.days) : 0);
    bars.replaceChildren(...st.timeline.map((b, i) => h("div", {
      class: "mv-bar" + (i >= from ? " is-in" : ""), style: { height: Math.max(3, (b.n / max) * 100) + "%" },
      title: `${b.day} · ${num(b.n)}` })));
    brushBox.style.left = (from / Math.max(1, span)) * 100 + "%";
    footer.querySelector(".mv-brush-range").textContent =
      st.timeline.length ? `${st.timeline[from]?.day || ""} — ${st.timeline[span - 1].day}` : "";
  }
  function brushDown(e) {
    const r = bars.getBoundingClientRect();
    const idx = (x) => Math.max(0, Math.min(st.timeline.length - 1, Math.floor(((x - r.left) / r.width) * st.timeline.length)));
    const move = (ev) => { st.brushFrom = idx(ev.clientX); paintBrush(); };
    const up = () => {
      window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
      st.days = st.timeline.length - st.brushFrom; st.autoFit = true; load();
    };
    move(e);
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  }

  // ── DOM ───────────────────────────────────────────────────────────────────────────────────────────────
  const zoomBtn = (key, glyph, fn) => h("button", { class: "hb-iconbtn hb-iconbtn--framed hb-iconbtn--lg", type: "button",
                                                    "aria-label": () => t(key), title: () => t(key), onClick: fn }, glyph);
  const el = h("div", { class: "mv-graph" },
    h("div", { class: "hb-toolbar hb-toolbar--sub mv-filters" },
      h("div", { class: "mv-seg", role: "group", "aria-label": () => t("memory.period_label"), ref: (x) => (periodEl = x) },
        ...PERIODS.map((p) => h("button", { type: "button", "data-days": String(p.days), "aria-pressed": "false",
                                            onClick: () => setPeriod(p.days) }, () => t(p.key)))),
      h("div", { class: "mv-layers", role: "group", "aria-label": () => t("memory.layers_label"), ref: (x) => (chipsEl = x) }),
      h("span", { class: "hb-toolbar-spacer" }),
      h("p", { class: "mv-showing", ref: (x) => (showingEl = x) }),
      h("button", { class: "hb-btn hb-btn--ghost hb-btn--sm", type: "button", "aria-pressed": "true",
                    onClick: (e) => { st.labels = !st.labels; e.currentTarget.setAttribute("aria-pressed", String(st.labels)); schedule(); } },
        () => t("memory.labels_toggle")),
      h("button", { class: "hb-btn hb-btn--sm", type: "button", onClick: exportPng }, () => t("memory.export_png")),
    ),
    h("div", { class: "mv-graph-body" },
      h("section", { class: "mv-canvas-wrap", "aria-label": () => t("memory.graph_label"), ref: (x) => (section = x) },
        h("canvas", { class: "mv-canvas", ref: (x) => (canvas = x), onWheel, onPointerdown: onDown, onPointermove: onMove,
                      role: "img", "aria-label": () => t("memory.graph_label") }),
        h("p", { class: "hb-empty-state mv-graph-empty", hidden: true, ref: (x) => (emptyEl = x) }),
        h("div", { class: "mv-legend" },
          h("span", {}, h("i", { class: "mv-dot mv-dot--hub" }), () => t("memory.legend_concept")),
          h("span", {}, h("i", { class: "mv-dot" }), () => t("memory.legend_memory")),
          h("span", { class: "mv-legend-long" }, () => t("memory.legend_size")),
          h("span", { class: "mv-legend-long" }, () => t("memory.legend_width"))),
        h("div", { class: "mv-zoom" },
          zoomBtn("memory.zoom_in", "+", () => zoomAt(1.25, canvas.clientWidth / 2, canvas.clientHeight / 2)),
          zoomBtn("memory.zoom_out", "−", () => zoomAt(0.8, canvas.clientWidth / 2, canvas.clientHeight / 2)),
          zoomBtn("memory.fit", "⤢", () => { st.autoFit = true; fit(); schedule(); })),
      ),
      h("aside", { class: "mv-detail", "aria-label": () => t("memory.detail_label"), ref: (x) => (aside = x) },
        h("div", { class: "mv-detail-head", ref: (x) => (detailHead = x) }),
        h("ul", { class: "mv-detail-list", ref: (x) => (detailList = x) })),
    ),
    h("footer", { class: "mv-brush", ref: (x) => (footer = x) },
      h("div", { class: "mv-brush-head" }, h("span", {}, () => t("memory.brush_label")), h("span", { class: "mv-brush-range" })),
      h("div", { class: "mv-brush-track", onPointerdown: brushDown },
        h("div", { class: "mv-bars", ref: (x) => (bars = x) }),
        h("div", { class: "mv-brush-box", ref: (x) => (brushBox = x) }))),
  );
  void aside;

  // The SECTION is observed, not the tab: the panel beside it (or under it, on a phone) changes the section's size
  // without the tab changing its own — measured at 375px, where the canvas kept a stale height.
  const ro = new ResizeObserver(() => { if (active) resize(); });
  ro.observe(section);

  return {
    el,
    activate() {
      active = true;
      resize();
      if (!st.data) { load(); loadTimeline(); } else schedule();
    },
    deactivate() { active = false; },
    refresh() { if (active) load(true); },
    pulse(ids) {
      const until = performance.now() + 4000;
      for (const id of ids || []) st.pulses.set(Number(id), until);
      if (active) schedule();
    },
    close() { stopWorker(); },
  };
}
