// ============================================================================
// memory/force-worker.js — the graph's force layout, OFF the main thread, and it STOPS when it settles (V2-808).
//
// Message in:  { nodes: [{r, hub, x?, y?}], links: [{s, t, w, len}] }  (indices into nodes)
// Messages out: { type: "tick", pos: Float32Array[x0,y0,x1,y1…], alpha } every few ticks, then
//               { type: "settled", pos } once — after that the worker does nothing until it is given a new graph.
//
// The forces, in order of cost:
//   · hubs (concepts) repel every other hub — k² with k ≤ 300;
//   · every node pushes away the nodes in its own and the eight neighbouring cells of a uniform grid — a short
//     range collision that is O(n) per tick, so a laptop's 1.500 nodes cost what 1.500 nodes cost, not 2,25 M;
//   · links pull to their rest length, the pull split by degree; a weak gravity keeps the whole thing around the origin.
// Cooling is the usual alpha decay (≈300 ticks from 1 to the floor); a warm start (positions given) begins cooler.
// ============================================================================

let run = 0;

self.onmessage = (ev) => {
  const g = ev.data || {};
  run++;
  layout(g, run);
};

function layout(g, myRun) {
  const nodes = g.nodes || [], links = g.links || [];
  const n = nodes.length;
  const x = new Float32Array(n), y = new Float32Array(n), vx = new Float32Array(n), vy = new Float32Array(n);
  const r = new Float32Array(n);
  let warm = 0;
  const hubs = [];
  for (let i = 0; i < n; i++) {
    const nd = nodes[i];
    r[i] = nd.r || 4;
    if (nd.hub) hubs.push(i);
    if (Number.isFinite(nd.x) && Number.isFinite(nd.y)) { x[i] = nd.x; y[i] = nd.y; warm++; }
    else {   // phyllotaxis seed: deterministic, spread, no two nodes on the same point
      const a = i * 2.39996, d = 12 * Math.sqrt(i + 0.5);
      x[i] = Math.cos(a) * d; y[i] = Math.sin(a) * d;
    }
  }
  const deg = new Float32Array(n);
  for (const l of links) { deg[l.s]++; deg[l.t]++; }
  let alpha = warm > n * 0.6 ? 0.3 : 1;
  const ALPHA_MIN = 0.004, DECAY = 1 - Math.pow(ALPHA_MIN, 1 / 300), FRICTION = 0.6;
  const CELL = 36;
  let tick = 0;

  const step = () => {
    if (myRun !== run) return;                 // a newer graph arrived: this one is abandoned
    for (let k = 0; k < 4 && alpha > ALPHA_MIN; k++) {
      // hub ↔ hub repulsion
      for (let a = 0; a < hubs.length; a++) {
        const i = hubs[a];
        for (let b = a + 1; b < hubs.length; b++) {
          const j = hubs[b];
          let dx = x[j] - x[i], dy = y[j] - y[i];
          let d2 = dx * dx + dy * dy;
          if (d2 < 1) { dx = (i - j) * 0.01 + 0.5; dy = 0.5; d2 = 1; }
          const f = (-900 * alpha) / d2;
          vx[i] += dx * f; vy[i] += dy * f; vx[j] -= dx * f; vy[j] -= dy * f;
        }
      }
      // short-range collision on a grid
      const grid = new Map();
      for (let i = 0; i < n; i++) {
        const key = ((x[i] / CELL) | 0) + ":" + ((y[i] / CELL) | 0);
        let cell = grid.get(key);
        if (!cell) grid.set(key, (cell = []));
        cell.push(i);
      }
      for (let i = 0; i < n; i++) {
        const cx = (x[i] / CELL) | 0, cy = (y[i] / CELL) | 0;
        for (let ox = -1; ox <= 1; ox++) for (let oy = -1; oy <= 1; oy++) {
          const cell = grid.get((cx + ox) + ":" + (cy + oy));
          if (!cell) continue;
          for (const j of cell) {
            if (j <= i) continue;
            const dx = x[j] - x[i], dy = y[j] - y[i];
            const min = r[i] + r[j] + 6;
            const d2 = dx * dx + dy * dy;
            if (d2 >= min * min) continue;
            const d = Math.sqrt(d2) || 0.01, push = ((min - d) / d) * 0.5 * Math.min(1, alpha * 4);
            vx[i] -= dx * push; vy[i] -= dy * push; vx[j] += dx * push; vy[j] += dy * push;
          }
        }
      }
      // springs — split by degree, so a hub with hundreds of memories is not yanked by every one of them at
      // once (unsplit, 287 springs on one concept overshot it into Infinity within 40 ticks — measured)
      for (const l of links) {
        const i = l.s, j = l.t;
        const dx = x[j] - x[i], dy = y[j] - y[i];
        const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const f = ((d - (l.len || 60)) / d) * alpha * (l.k || 0.08);
        const b = deg[i] / (deg[i] + deg[j]);
        vx[i] += dx * f * (1 - b); vy[i] += dy * f * (1 - b); vx[j] -= dx * f * b; vy[j] -= dy * f * b;
      }
      // gravity + integrate
      for (let i = 0; i < n; i++) {
        vx[i] -= x[i] * 0.008 * alpha; vy[i] -= y[i] * 0.008 * alpha;
        vx[i] *= FRICTION; vy[i] *= FRICTION;
        // a velocity cap: one bad tick can push a node far, never to Infinity (a canvas refuses non-finite input)
        if (!(Math.abs(vx[i]) < 400)) vx[i] = Number.isFinite(vx[i]) ? Math.sign(vx[i]) * 400 : 0;
        if (!(Math.abs(vy[i]) < 400)) vy[i] = Number.isFinite(vy[i]) ? Math.sign(vy[i]) * 400 : 0;
        x[i] += vx[i]; y[i] += vy[i];
      }
      alpha *= 1 - DECAY;
      tick++;
    }
    const pos = new Float32Array(n * 2);
    for (let i = 0; i < n; i++) { pos[2 * i] = x[i]; pos[2 * i + 1] = y[i]; }
    if (alpha <= ALPHA_MIN) {
      self.postMessage({ type: "settled", pos, ticks: tick }, [pos.buffer]);
      return;                                  // settled: no timer left behind
    }
    self.postMessage({ type: "tick", pos, alpha }, [pos.buffer]);
    setTimeout(step, 0);
  };
  step();
}
