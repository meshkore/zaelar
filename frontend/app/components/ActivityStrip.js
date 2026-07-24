// ActivityStrip — the BACKGROUND-ACTIVITY layer: a HONEYCOMB of dark hexagons at the very BACK of the canvas
// (V2-039 redesign, operator 2026-07-17). Every in-flight background task (widget build/modify, web task, worker
// phase, deep reasoning) is ONE hexagon with the current doing-text inside ("pensando…", "buscando en la web…",
// "entrando en wallapop…"). Cells GLUE to the existing cluster — the first sits at the screen centre, each new one
// picks a RANDOM free side of the cluster, and if a direction doesn't fit on screen it grows another way (never
// leaves the viewport). When a task ends its hexagon fades away and frees the cell. Styled as a VERY dark grey
// lift over the dark canvas — ambient "things are happening", not a notification: the user needn't read it, and
// widgets/orb paint OVER it (the layer mounts right above .canvas, below .wstage; pointer-events:none).
// Replaces the old liquid blobs flanking the orb (they collided with the orb/ECG and read as clutter).
// Fed by store.tasks (← SSE "task" events + GET /api/tasks reconcile) — same contract, only the rendering changed.
import { h, raw } from "../core/dom.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";

// ---- hex geometry (flat-top, axial coords) — PURE helpers, exported for headless tests ----
export const DIRS = [[1, 0], [1, -1], [0, -1], [-1, 0], [-1, 1], [0, 1]];
const SQ3 = Math.sqrt(3);

export const hexPx = (q, r, rad, vw, vh) => ({
  x: vw / 2 + 1.5 * rad * q,
  y: vh / 2 + SQ3 * rad * (r + q / 2),
});
export const hexFits = (q, r, rad, vw, vh) => {
  const { x, y } = hexPx(q, r, rad, vw, vh), hh = (SQ3 * rad) / 2;
  return x - rad >= 6 && x + rad <= vw - 6 && y - hh >= 6 && y + hh <= vh - 6;
};
// ring n of cells around the origin (cube-walk) — fallback scan order when the cluster has no free glued side
export function* hexRing(n) {
  if (n === 0) { yield [0, 0]; return; }
  let q = DIRS[4][0] * n, r = DIRS[4][1] * n;
  for (let i = 0; i < 6; i++) for (let j = 0; j < n; j++) { yield [q, r]; q += DIRS[i][0]; r += DIRS[i][1]; }
}
// Pick the cell for a NEW task: a random free ON-SCREEN neighbour of the cluster (glued growth in a random
// direction); with no cluster (or a fully boxed-in one) → the free on-screen cell nearest the centre.
export function hexPlace(occ, rad, vw, vh, rnd = Math.random) {
  if (occ.size) {
    const cands = [];
    for (const key of occ) {
      const [q, r] = key.split(",").map(Number);
      for (const [dq, dr] of DIRS) {
        const nq = q + dq, nr = r + dr;
        if (!occ.has(nq + "," + nr) && hexFits(nq, nr, rad, vw, vh)) cands.push([nq, nr]);
      }
    }
    if (cands.length) return cands[(rnd() * cands.length) | 0];
  }
  for (let n = 0; n <= 24; n++) for (const [q, r] of hexRing(n)) if (!occ.has(q + "," + r) && hexFits(q, r, rad, vw, vh)) return [q, r];
  return [0, 0];   // pathological viewport → centre (clipped is better than lost)
}

// flat-top hexagon inset ~2px inside its 200×173.2 box (a hairline gap keeps glued cells readable as cells)
const HEX_SVG = `<svg viewBox="0 0 200 173.2" preserveAspectRatio="none"><polygon points="197.5,86.6 148.8,171 51.3,171 2.5,86.6 51.3,2.2 148.8,2.2"/></svg>`;

export function ActivityStrip() {
  const layer = h("div", { class: "hexbg", "aria-hidden": "true" });
  const cells = new Map();   // task id → { q, r, el }
  const rad = () => (innerWidth < 620 ? 56 : 82);

  const layout = (el, q, r) => {
    const rr = rad(), { x, y } = hexPx(q, r, rr, innerWidth, innerHeight), hh = SQ3 * rr;
    el.style.left = (x - rr) + "px"; el.style.top = (y - hh / 2) + "px";
    el.style.width = (2 * rr) + "px"; el.style.height = hh + "px";
  };

  const drop = (id) => {
    const c = cells.get(id);
    if (!c) return;
    cells.delete(id);                                   // free the cell NOW (a new task can glue there)
    c.el.classList.add("out");
    setTimeout(() => c.el.remove(), 520);
  };

  createEffect(() => {
    const ts = store.tasks();
    const seen = new Set();
    for (const t of ts) {
      const id = String(t.id);
      seen.add(id);
      let c = cells.get(id);
      if (!c && !t.done) {
        const occ = new Set([...cells.values()].map(v => v.q + "," + v.r));
        const [q, r] = hexPlace(occ, rad(), innerWidth, innerHeight);
        const el = h("div", { class: "hexcell" }, raw(HEX_SVG),
          h("div", { class: "hextext" }, h("span", { class: "hextxt" })));
        el.style.animationDelay = (-(Math.random() * 4)).toFixed(2) + "s";   // desync the breathing
        layout(el, q, r);
        layer.appendChild(el);
        requestAnimationFrame(() => el.classList.add("in"));
        c = { q, r, el };
        cells.set(id, c);
      }
      if (!c) continue;
      const txt = (t.waiting ? "❔ " : "") + (t.text || "…");
      const span = c.el.querySelector(".hextxt");
      if (span && span.textContent !== txt) { span.textContent = txt; c.el.title = t.text || ""; }
      c.el.classList.toggle("asking", !!t.waiting);
      if (t.done) drop(id);                             // settled → fade the cell away
    }
    for (const id of [...cells.keys()]) if (!seen.has(id)) drop(id);   // reconciled away → free the cell
  });

  // keep the cluster centred on resize (axial coords are viewport-relative)
  window.addEventListener("resize", () => cells.forEach(c => layout(c.el, c.q, c.r)));

  return layer;
}
