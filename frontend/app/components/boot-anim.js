// ============================================================================
// boot-anim.js — “Colmena sináptica”: the boot splash animation engine.
//
// A neural constellation that ASSEMBLES ITSELF IN PARTS — one cluster of nodes
// lights up per boot phase (encendiendo → voz → memory → reflejo) — then, on
// "listo", the whole mesh IMPLODES gracefully into the orb, handing off to the
// live voice visualiser. Geometric (a Delaunay-ish neighbour mesh) AND liquid
// (curl-noise drift + a gradient shimmer travelling the edges).
//
// Self-contained: pure <canvas>, no deps. Colours come from the --hb-* theme
// tokens, so it works in dark and light. Honours prefers-reduced-motion.
//
// Contract: startBootAnim(canvas, { onDone }) → { setPhase(phase), destroy() }.
// The DOM lifecycle (mount/unmount, phase wiring) lives in BootOverlay.js; this
// file is JUST the render engine and knows nothing about the store.
// ============================================================================

// Phases that light up a cluster, in order. "listo" is the implosion, handled apart.
const ASSEMBLY = ["encendiendo", "voz", "memoria", "reflejo"];
const NODE_COUNT = 240;          // cheap: a few hundred points + nearest-neighbour edges
const NEIGHBOURS = 3;            // edges per node (to its nearest N)
// LIVING BRAIN (V2-039): while we WAIT on a phase (voice can take ~30s), the lit mesh must feel ALIVE — neurons
// fire spontaneously and the spark travels the synapses to their neighbours, which fire in turn (a decaying
// cascade). These knobs pace that activity so it reads as "thinking", not noise.
const IGNITE_RATE = 3.2;         // spontaneous neuron firings per second (over the LIT mesh)
const PULSE_DUR = 0.34;          // seconds a synapse spark takes to travel one edge
const PULSE_FANOUT = 3;          // max neighbours a firing neuron sparks at once
const CASCADE_DECAY = 0.52;      // energy kept when a spark arrives and re-fires the next neuron (→ chains fade)
const CASCADE_MIN = 0.12;        // below this energy a spark dies (stops the cascade)
const MAX_PULSES = 90;           // hard cap on in-flight sparks (perf guard)
const FIRE_DECAY = 2.8;          // how fast a neuron's flare fades (per second)
// PIECE-BY-PIECE ASSEMBLAnd (V2-039): the brain COMPOSES itself gradually — ~240 tiny pieces revealed one after
// another, growing from the centre outward — like a 0→100 progress. Each boot phase sets a reveal target; the
// progress CATCHES UP fast when a phase advances (quick load → pieces pop in fast) and TRICKLES slowly while we're
// stuck on one initialisation (voice can take ~30s), so it never freezes "at half" — it keeps building. `soft` =
// where the fast catch-up aims; `hard` = the slow ceiling it creeps to during a stall (kept below the next phase).
const PHASE_SOFT = { encendiendo: 0.20, voz: 0.50, memoria: 0.74, reflejo: 0.92 };
const PHASE_HARD = { encendiendo: 0.32, voz: 0.64, memoria: 0.86, reflejo: 0.98 };
const REVEAL_CATCHUP = 0.9;      // how hard `progress` chases `soft` (fast reveal on a phase jump)
const REVEAL_TRICKLE = 0.013;    // constant slow creep up to `hard` (keeps pieces appearing during a long stall)

function cssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

// Parse a CSS colour (hex or rgb[a]) to [r,g,b]. Falls back to a mid grey.
function toRGB(str) {
  const s = (str || "").trim();
  let m = s.match(/^#([0-9a-f]{3})$/i);
  if (m) { const h = m[1]; return [h[0], h[1], h[2]].map(c => parseInt(c + c, 16)); }
  m = s.match(/^#([0-9a-f]{6})$/i);
  if (m) return [0, 2, 4].map(i => parseInt(m[1].slice(i, i + 2), 16));
  m = s.match(/rgba?\(([^)]+)\)/i);
  if (m) return m[1].split(",").slice(0, 3).map(n => parseInt(n, 10));
  return [120, 140, 170];
}
const rgba = ([r, g, b], a) => `rgba(${r},${g},${b},${a})`;
const lerp = (a, b, t) => a + (b - a) * t;
const lerpRGB = (a, b, t) => [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];
const easeOut = t => 1 - Math.pow(1 - t, 3);
const easeInOut = t => t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

export function startBootAnim(canvas, { onDone } = {}) {
  const ctx = canvas.getContext("2d");
  const reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  let W = 0, H = 0, dpr = 1;
  let cx = 0, cy = 0, span = 0;             // constellation centre + radius, set on resize
  const accent = toRGB(cssVar("--hb-accent", "#3D6FE0"));
  const accent2 = toRGB(cssVar("--hb-accent2", "#8B5CF6"));
  const bg = toRGB(cssVar("--hb-bg", "#0d1622"));

  const nodes = [];   // {hx,hy, x,y, cl, seed, act, ripple, fire}
  let edges = [];     // [i, j, dist]
  let adj = [];       // adjacency: node index → [neighbour indices] (for synaptic propagation)
  const pulses = [];  // in-flight synapse sparks: {i, j, t(0..1), dur, energy}
  let igniteAcc = 0;  // fractional accumulator for the spontaneous-firing rate
  let lastT = 0;      // previous frame time (s) → real dt, framerate-independent
  let order = [];             // reveal sequence (node indices) — grown from the centre outward, so it assembles organically
  let progress = 0;           // 0..1 fraction of the brain revealed → drives the piece-by-piece assembly
  let soft = 0, hard = 0;     // current phase's reveal target: fast catch-up to `soft`, slow trickle up to `hard`
  let imploding = false, implodeStart = 0, target = null, done = false;
  let raf = 0, t0 = 0;

  function layout() {
    const r = canvas.getBoundingClientRect();
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = r.width; H = r.height;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    cx = W / 2; cy = H * 0.46; span = Math.min(W, H) * 0.34;
    // Place nodes over an organic elliptical disk (brain-ish). No wedges: the reveal ORDER (computed below) grows
    // the mesh piece by piece from the centre outward, so it assembles as one organism rather than in quadrants.
    if (!nodes.length) {
      for (let i = 0; i < NODE_COUNT; i++) {
        const a = Math.random() * Math.PI * 2;
        const rad = Math.sqrt(Math.random());        // uniform over the disk
        nodes.push({ a, rad, x: 0, y: 0, hx: 0, hy: 0, ord: 0, seed: Math.random() * 1000, act: 0, ripple: -1, fire: 0 });
      }
    }
    // (re)compute home positions on the current viewport (ellipse a bit wider than tall)
    for (const n of nodes) {
      n.hx = cx + Math.cos(n.a) * n.rad * span * 1.5;
      n.hy = cy + Math.sin(n.a) * n.rad * span * 1.05;
      if (n.act === 0) { n.x = n.hx; n.y = n.hy; }
    }
    // GROWTH ORDER (once): reveal the node nearest the CENTRE first, then repeatedly the unrevealed node closest to
    // whatever's already revealed (Prim-like) → the brain grows outward in organic tendrils, "montando pieza a pieza".
    if (!order.length) {
      const n = nodes.length, used = new Array(n).fill(false), mind = new Array(n).fill(Infinity);
      let seed = 0, best = Infinity;
      for (let i = 0; i < n; i++) { const dx = nodes[i].hx - cx, dy = nodes[i].hy - cy, d = dx * dx + dy * dy; if (d < best) { best = d; seed = i; } }
      const relax = (from) => { for (let i = 0; i < n; i++) if (!used[i]) { const dx = nodes[i].hx - nodes[from].hx, dy = nodes[i].hy - nodes[from].hy, d = dx * dx + dy * dy; if (d < mind[i]) mind[i] = d; } };
      used[seed] = true; order.push(seed); relax(seed);
      for (let k = 1; k < n; k++) {
        let pick = -1, pb = Infinity;
        for (let i = 0; i < n; i++) if (!used[i] && mind[i] < pb) { pb = mind[i]; pick = i; }
        if (pick < 0) break;
        used[pick] = true; order.push(pick); relax(pick);
      }
      order.forEach((idx, rank) => { nodes[idx].ord = rank; });   // each node remembers its place in the sequence
    }
    // nearest-neighbour edges (recomputed on layout; O(n²) once, n=240 → fine)
    edges = [];
    for (let i = 0; i < nodes.length; i++) {
      const d = [];
      for (let j = 0; j < nodes.length; j++) if (j !== i) {
        const dx = nodes[i].hx - nodes[j].hx, dy = nodes[i].hy - nodes[j].hy;
        d.push([j, dx * dx + dy * dy]);
      }
      d.sort((a, b) => a[1] - b[1]);
      for (let k = 0; k < NEIGHBOURS; k++) if (d[k] && i < d[k][0]) edges.push([i, d[k][0], Math.sqrt(d[k][1])]);
    }
    // adjacency for synaptic propagation (each edge is bidirectional for firing)
    adj = nodes.map(() => []);
    for (const [i, j] of edges) { adj[i].push(j); adj[j].push(i); }
  }

  // A neuron FIRES: flare up, ripple, and shoot synapse sparks down a few of its LIT edges. Only lit neurons fire
  // (act>threshold) — during the wait the lit clusters buzz; a dark cluster stays quiet until its phase powers on.
  function ignite(idx, energy) {
    const n = nodes[idx];
    if (!n || n.act <= 0.05) return;
    n.fire = Math.min(1.5, n.fire + energy);
    n.ripple = 0;
    if (reduced || pulses.length >= MAX_PULSES) return;   // reduced-motion: flare only, no travelling sparks
    let count = 0;
    for (const j of adj[idx]) {
      if (count >= PULSE_FANOUT || pulses.length >= MAX_PULSES) break;
      if (nodes[j].act > 0.05 && Math.random() < 0.72) {
        pulses.push({ i: idx, j, t: 0, dur: PULSE_DUR * (0.8 + Math.random() * 0.5), energy });
        count++;
      }
    }
  }

  function litIndices() {
    const out = [];
    for (let i = 0; i < nodes.length; i++) if (nodes[i].act > 0.4) out.push(i);
    return out;
  }

  function orbTarget() {
    const orb = document.getElementById("orb");
    if (orb) { const r = orb.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; }
    return { x: W / 2, y: H - 80 };   // fallback: bottom-centre where the orb lives
  }

  function setPhase(phase) {
    if (phase === "listo") {
      if (imploding) return;
      progress = 1;                                                            // reveal whatever's left, fast…
      nodes.forEach(n => { if (n.act === 0) { n.act = 0.001; n.ripple = 0; } });// …ensure everything is lit for the collapse
      imploding = true; implodeStart = performance.now(); target = orbTarget();
      return;
    }
    // Raise the reveal target for this phase (never lower it — phases only move forward). `progress` chases it in frame().
    soft = Math.max(soft, PHASE_SOFT[phase] || soft);
    hard = Math.max(hard, PHASE_HARD[phase] || hard);
  }

  function frame(now) {
    if (!t0) t0 = now;
    const t = (now - t0) / 1000;
    const dt = Math.min(0.05, Math.max(0, t - lastT));   // real, framerate-independent step (capped after a stall)
    lastT = t;

    // LIVING BRAIN: spontaneously fire lit neurons at a steady rate while we're still assembling/waiting (not while
    // imploding — then the mesh is collapsing into the orb). The spark travels the synapses and re-fires neighbours.
    if (!reduced && !imploding) {
      igniteAcc += dt * IGNITE_RATE;
      if (igniteAcc >= 1) {
        const lit = litIndices();
        while (igniteAcc >= 1) {
          igniteAcc -= 1;
          if (lit.length) ignite(lit[(Math.random() * lit.length) | 0], 0.9 + Math.random() * 0.5);
        }
      }
    }

    // subtle trail for the "liquid light" comet feel (bg-tinted wash instead of a hard clear)
    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = rgba(bg, reduced ? 1 : 0.30);
    ctx.fillRect(0, 0, W, H);

    // implosion progress
    let imp = 0;
    if (imploding) {
      imp = Math.min(1, (now - implodeStart) / 780);
      if (imp >= 1 && !done) { done = true; cancelAnimationFrame(raf); ctx.clearRect(0, 0, W, H); onDone && onDone(); return; }
    }

    // ASSEMBLY: advance the reveal progress (fast catch-up to `soft` on a phase jump + slow trickle up to `hard`
    // during a stall) and switch on the next pieces in growth order → the brain builds itself continuously.
    if (!imploding) {
      const gap = Math.max(0, soft - progress);
      progress = Math.min(hard, progress + (gap * REVEAL_CATCHUP + REVEAL_TRICKLE) * dt);
    }
    const shown = progress * NODE_COUNT;

    // advance node activation + drift, compute drawn positions
    for (const n of nodes) {
      if (n.act === 0 && n.ord < shown) { n.act = 0.001; n.ripple = 0; }   // this piece's turn to appear
      if (n.act > 0 && n.act < 1) n.act = Math.min(1, n.act + 0.045);
      if (n.fire > 0) n.fire = Math.max(0, n.fire - dt * FIRE_DECAY);   // the flare fades after a neuron fires
      if (n.ripple >= 0) { n.ripple += 0.04; if (n.ripple > 1) n.ripple = -1; }
      // curl-ish drift around home (organic / liquid)
      const drift = reduced ? 0 : 6;
      let x = n.hx + Math.sin(t * 0.6 + n.seed) * drift + Math.cos(t * 0.37 + n.seed * 1.7) * drift * 0.6;
      let y = n.hy + Math.cos(t * 0.5 + n.seed * 1.3) * drift + Math.sin(t * 0.41 + n.seed) * drift * 0.6;
      if (imploding) {
        const e = easeInOut(imp);
        x = lerp(x, target.x, e); y = lerp(y, target.y, e);
      }
      n.x = x; n.y = y;
    }

    // edges — only when both endpoints are lit; gradient shimmer travelling along the mesh
    ctx.lineWidth = 1;
    for (const [i, j] of edges) {
      const a = nodes[i], b = nodes[j];
      const lit = Math.min(a.act, b.act);
      if (lit <= 0.02) continue;
      const fade = imploding ? (1 - imp) : 1;
      // shimmer: a phase that runs along the edge over time → colour lerps accent↔accent2
      const sh = 0.5 + 0.5 * Math.sin(t * 1.6 - (i + j) * 0.25);
      const col = lerpRGB(accent, accent2, sh);
      ctx.strokeStyle = rgba(col, 0.10 * lit * fade);
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      // a faint ambient drift dot for the "liquid" flow (the LOUD life is the firing sparks below)
      if (!reduced && !imploding && lit > 0.6) {
        const tp = (t * 0.4 + (i * 0.13 + j * 0.07)) % 1;
        const px = lerp(a.x, b.x, tp), py = lerp(a.y, b.y, tp);
        ctx.fillStyle = rgba(col, 0.28 * lit);
        ctx.beginPath(); ctx.arc(px, py, 1.2, 0, Math.PI * 2); ctx.fill();
      }
    }

    // SYNAPSE SPARKS — bright comets travelling from a fired neuron to its neighbours; on arrival they re-fire the
    // next neuron with decayed energy (a cascade that fades). Additive blend so overlaps bloom like real activity.
    if (pulses.length) {
      ctx.globalCompositeOperation = "lighter";
      for (let p = pulses.length - 1; p >= 0; p--) {
        const pu = pulses[p];
        pu.t += dt / pu.dur;
        const a = nodes[pu.i], b = nodes[pu.j];
        const done2 = pu.t >= 1;
        const tp = done2 ? 1 : pu.t;
        const px = lerp(a.x, b.x, tp), py = lerp(a.y, b.y, tp);
        const sh = 0.5 + 0.5 * Math.sin(t * 1.6 - (pu.i + pu.j) * 0.25);
        const col = lerpRGB(accent, accent2, sh);
        const fade = imploding ? (1 - imp) : 1;
        const rad = 2.2 * pu.energy;
        const g = ctx.createRadialGradient(px, py, 0, px, py, 7 * pu.energy);
        g.addColorStop(0, rgba(col, 0.9 * pu.energy * fade));
        g.addColorStop(1, rgba(col, 0));
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(px, py, 7 * pu.energy, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = rgba([236, 242, 255], 0.9 * pu.energy * fade);
        ctx.beginPath(); ctx.arc(px, py, rad, 0, Math.PI * 2); ctx.fill();
        if (done2) {
          pulses.splice(p, 1);
          const next = pu.energy * CASCADE_DECAY;
          if (!imploding && next > CASCADE_MIN) ignite(pu.j, next);   // the spark lands → the neighbour fires
        }
      }
      ctx.globalCompositeOperation = "source-over";
    }

    // nodes — glow + core; a ripple ring on the frame a cluster switched on
    for (const n of nodes) {
      if (n.act <= 0) continue;
      const fade = imploding ? (1 - imp * 0.6) : 1;
      const fl = Math.min(1, n.fire);                       // 0..1 flare when the neuron just fired
      const r = ((imploding ? 1.6 + 2 * (1 - imp) : 1.8 + n.act) + fl * 2.4) * fade;
      const col = lerpRGB(accent, accent2, n.ord / NODE_COUNT);   // gradient sweeps along the growth order
      // the firing flare blooms additively so a burst reads as a bright synapse, then fades back to the calm glow
      const gr = 9 * n.act + fl * 13;
      const g = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, gr);
      g.addColorStop(0, rgba(lerpRGB(col, [255, 255, 255], fl * 0.6), (0.5 * n.act + fl * 0.55) * fade));
      g.addColorStop(1, rgba(col, 0));
      if (fl > 0.02) ctx.globalCompositeOperation = "lighter";
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(n.x, n.y, gr, 0, Math.PI * 2); ctx.fill();
      ctx.globalCompositeOperation = "source-over";
      ctx.fillStyle = rgba([245, 248, 255], Math.min(1, 0.85 * n.act + fl * 0.6) * fade);
      ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, Math.PI * 2); ctx.fill();
      if (n.ripple >= 0 && !imploding) {
        ctx.strokeStyle = rgba(col, 0.4 * (1 - n.ripple)); ctx.lineWidth = 1.2;
        ctx.beginPath(); ctx.arc(n.x, n.y, 4 + n.ripple * 22, 0, Math.PI * 2); ctx.stroke();
      }
    }

    // final flash at the orb as the mesh lands
    if (imploding && imp > 0.7) {
      const f = easeOut((imp - 0.7) / 0.3);
      const g = ctx.createRadialGradient(target.x, target.y, 0, target.x, target.y, 70 * f + 20);
      g.addColorStop(0, rgba(accent2, 0.5 * (1 - f)));
      g.addColorStop(1, rgba(accent2, 0));
      ctx.fillStyle = g; ctx.beginPath(); ctx.arc(target.x, target.y, 70 * f + 20, 0, Math.PI * 2); ctx.fill();
    }

    raf = requestAnimationFrame(frame);
  }

  const onResize = () => layout();
  layout();
  window.addEventListener("resize", onResize);
  // seed the first cluster right away so the mesh isn't blank on the first frame
  setPhase("encendiendo");
  raf = requestAnimationFrame(frame);

  return {
    setPhase,
    destroy() { cancelAnimationFrame(raf); window.removeEventListener("resize", onResize); },
  };
}
