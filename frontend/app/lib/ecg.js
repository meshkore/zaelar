// ============================================================================
// ecg.js — the orb's ELECTROCARDIOGRAM (V2-039). A heart monitor whose beat is
// zaelar's REAL pulse: each `loop.tick` from the orchestrator (nucleo/loop.py,
// ~1 Hz at rest — the server just checking crons/processes) draws one QRS
// complex. When zaelar is busy (background tasks in flight, FlashBrain turns
// closing) the rhythm ACCELERATES and the spikes grow — a resting heart that
// races when it thinks. Fed by store.pulse (bridged from the bus in
// server/__init__.py) + store.tasks()/botSpeaking() for the load.
//
// GEOMETRY (redesign 2026-07-16, operator): not a flat strip — the trace runs
// along a WIDE, GENTLE ARC cradling the orb from below, a MIRROR of the crown of
// icons arched over its top: same RADIUS OF CURVATURE (R ≈ 2.8·orbRadius, matching
// the crown's px splay) so orb + crown + pulse read as two halves of ONE circle.
// The arc's CENTRE sits well above it (cx,cy) — it's the bottom slice of a big
// circle, not a tight hug — so the bow is shallow and its shoulders reach WIDE.
// The R spikes point INWARD (toward the orb, "up" on the arc) and both tips
// DISSOLVE with a soft radial fade (destination-out) so the line never starts
// from nowhere or ends into nothing. Theme-aware via the --hb-* CSS vars. A
// FLAT arc means no real pulse is arriving (SSE down / BRAIN≠nucleo) — honest,
// never faked.
// ============================================================================
import * as store from "../core/store.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";

export function startEcg(canvas) {
  const dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
  const ctx = canvas.getContext("2d");

  // ---- THE ALMOND EYE (V2-039 «ojo» v4, operator 2026-07-22) ----
  // An eye is two curves meeting at the corners. This canvas draws ONLY the LOWER lid = the live ECG trace (the
  // pulse), a slice of the almond circle with its tips at the canthi on the orb's centre line (±S, orbY) and its
  // bow clearing the orb below (bottom at +a, a > half). The UPPER lid is NOT a stroke — it's the ICONS
  // themselves ("arriba van los iconos, no una raya"), laid out along the SAME circle by styles.css §orbctl
  // (same R = (S²+a²)/2a, same corners) so both lids close the almond with the orb as iris. Geometry recomputed
  // on resize; the whole orbwrap drags together, so the orb→canvas offset only changes on layout.
  let W = 0, H = 0;
  let cx = 0, cy = 0;          // LOWER-lid circle centre (above the orb — big radius, shallow bow)
  let R = 200;                 // radius of curvature (shared with the icon lid drawn by CSS)
  let AMP = 16;                // R-spike height in px (radially inward, kept clear of the orb's edge)
  let PHI = 0.6;               // half-arc in radians (tips at ±PHI = the canthi)
  let N = 0;                   // samples along the arc (~1px of arc length each)
  let pts = [], ux = [], uy = [];

  function resize() {
    const r = canvas.getBoundingClientRect();
    W = Math.max(80, Math.round(r.width));
    H = Math.max(40, Math.round(r.height));
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const orb = document.getElementById("orb");
    const or = orb ? orb.getBoundingClientRect() : null;
    const half = (or && or.width) ? or.width / 2 : 74;
    const orbX = (or && or.width) ? (or.left + or.width / 2 - r.left) : W / 2;
    const orbY = (or && or.width) ? (or.top + or.height / 2 - r.top) : -14;
    // Almond: corners (canthi) at (±S, orbY) — the orb's CENTRE LINE — apexes at ±a. a>half so both lids CLEAR
    // the orb (upper passes over its top, lower under its bottom) and the iris sits tucked between them.
    const S = Math.min(W / 2 - 10, half * 2.16);           // half-WIDTH of the eye (out to the corners)
    const a = half * 1.24;                                 // half-HEIGHT (apex above / below the orb's edge)
    R = (S * S + a * a) / (2 * a);                         // circle through (±S,0) and (0,∓a) → shared curvature
    PHI = Math.asin(Math.min(0.98, S / R));                // tips at ±PHI land exactly on the corners
    AMP = Math.max(12, half * 0.22);
    cx = orbX;
    cy = orbY + (a - R);                                   // lower-lid centre: tips at orbY, bow bottom at orbY+a
    N = Math.max(120, Math.round(2 * R * PHI));            // ≈ arc length in px → 1 sample per px
    if (pts.length !== N) pts = new Array(N).fill(0);
    ux = new Array(N); uy = new Array(N);
    for (let i = 0; i < N; i++) {
      const phi = -PHI + (i / (N - 1)) * 2 * PHI;
      ux[i] = Math.sin(phi); uy[i] = Math.cos(phi);        // unit vector from the lid's circle centre (y down)
    }
  }
  resize();
  const ro = new ResizeObserver(resize); ro.observe(canvas);

  // ---- classic PQRST as a function of beat phase p∈[0,1). Sum of gaussians; amp 1.0 → full R spike. ----
  const bell = (p, c, w, h) => h * Math.exp(-((p - c) * (p - c)) / (2 * w * w));
  function pqrst(p) {
    if (p < 0 || p >= 1) return 0;
    return bell(p, 0.16, 0.022, 0.14)   // P wave
         - bell(p, 0.30, 0.010, 0.16)   // Q dip
         + bell(p, 0.34, 0.012, 1.00)   // R spike
         - bell(p, 0.385, 0.012, 0.34)  // S dip
         + bell(p, 0.62, 0.045, 0.30);  // T wave
  }

  // ---- beat state (event + load driven). beatPhase===null → flat isoelectric baseline. ----
  const BEAT_SEC = 0.42;                            // seconds the PQRST complex spans on the trace
  const now = () => performance.now();
  let beatPhase = null, beatAmp = 0, lastBeatT = -1e9;

  function triggerBeat(amp, minGap = 240) {
    const t = now();
    if (t - lastBeatT < minGap) return;             // dedupe near-simultaneous beats (a tick + a turn)
    lastBeatT = t; beatPhase = 0; beatAmp = amp;
  }

  // store.pulse → a beat. tick = the real ~1 Hz server heartbeat (rest amplitude); turn = a FlashBrain turn (taller).
  //
  // PERO SOLO SI EL AGENTE ESTÁ VIVO (2026-08-10, fallo reportado por el operador con captura: «fíjate que está el
  // ECG a tope y el agente debería estar completamente parado»). El pulso que llega es del SERVIDOR (loop.tick de
  // nucleo/loop.py, ~1 Hz), y el servidor sigue latiendo aunque la sesión de voz esté apagada — así que el
  // electrocardiograma, que es lo que MÁS dice «estoy vivo» en toda la pantalla, seguía a pleno pulmón sobre un
  // agente detenido. Ahora un agente parado da una línea PLANA, que es la lectura honesta: no late porque no está.
  // (El arreglo de 2026-07-23 atacó solo los latidos EXTRA por carga —`activeLoad`—, no el pulso base.)
  let lastSeq = 0;
  createEffect(() => {
    const p = store.pulse();
    if (!p || p.seq === lastSeq) return;
    lastSeq = p.seq;                          // se consume igual: al volver a encender no se descarga la cola
    if (!store.agentLive()) return;
    triggerBeat(p.kind === "turn" ? 1.15 : 0.85);
  });

  // V2-065: una tarea PAUSADA (⏻) está deliberadamente congelada — no debe seguir acelerando el pulso, o
  // "apagar" contradiría su propia señal visual (el pulso seguiría corriendo mientras todo está quieto).
  const activeLoad = () =>
    store.agentLive()      // parado = ni latido base ni latidos por carga: la línea se queda plana de verdad
      ? (store.tasks() || []).filter(t => !t.done && !t.paused).length + (store.botSpeaking() ? 1 : 0)
      : 0;

  // ---- render loop ----
  const PX_PER_SEC = 92;                            // trace scroll speed (px of arc length per second)
  let last = now(), acc = 0, raf = null;

  function css(v, fb) {
    return (getComputedStyle(document.documentElement).getPropertyValue(v) || "").trim() || fb;
  }

  function frame() {
    const t = now(); const dt = Math.min(0.05, (t - last) / 1000); last = t;
    const load = activeLoad();

    // Under load, insert beats BETWEEN the real ticks so the rhythm RACES — the resting rhythm stays the true
    // server pulse (driven only by loop.tick events), we just add extra QRS as work piles up.
    if (load > 0) {
      const interval = Math.max(360, 900 / (1 + load * 0.8));   // ms between beats; more load → shorter RR
      if (t - lastBeatT >= interval) triggerBeat(0.9 + Math.min(load, 4) * 0.06, interval * 0.6);
    }

    // advance the trace, synthesising the new columns at the arc's right tip
    acc += dt * PX_PER_SEC;
    const step = 1 / (BEAT_SEC * PX_PER_SEC);        // phase advance per generated column
    while (acc >= 1) {
      acc -= 1;
      let y = 0;
      if (beatPhase !== null) {
        y = pqrst(beatPhase) * beatAmp;
        beatPhase += step;
        if (beatPhase >= 1) beatPhase = null;
      }
      pts.push(y); if (pts.length > N) pts.shift();
    }

    draw();
    raf = requestAnimationFrame(frame);
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);
    if (!N) return;
    const accent = css("--hb-accent", "#2DD4BF");
    ctx.lineJoin = "round"; ctx.lineCap = "round";
    // LOWER LID = the live ECG trace (the pulse) — the ONLY stroke this canvas draws (operator 2026-07-22: "abajo
    // del ojo va el pulso, y arriba van los iconos, no una raya"). The UPPER lid is formed by the ICONS themselves,
    // laid out along this same almond circle by the CSS in styles.css §orbctl — same R, same corners.
    ctx.lineWidth = 1.7; ctx.strokeStyle = accent;
    ctx.shadowColor = accent; ctx.shadowBlur = 7;
    ctx.beginPath();
    for (let i = 0; i < N; i++) {
      const rad = R - pts[i] * AMP;
      const x = cx + ux[i] * rad, y = cy + uy[i] * rad;
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
    ctx.stroke();
    ctx.shadowBlur = 0;
    // Tiny SOFT fade right at the meeting corners (the lids now CLOSE the shape — no more dissolving tips, just
    // a whisper of softness where they join so the canthi don't look like hard X crossings).
    const FADE = 14;
    ctx.globalCompositeOperation = "destination-out";
    for (const i of [0, N - 1]) {
      const x = cx + ux[i] * R, y = cy + uy[i] * R;
      const g = ctx.createRadialGradient(x, y, 0, x, y, FADE);
      g.addColorStop(0, "rgba(0,0,0,.85)");
      g.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(x, y, FADE, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalCompositeOperation = "source-over";
  }

  raf = requestAnimationFrame(frame);
  return () => { if (raf) cancelAnimationFrame(raf); ro.disconnect(); };
}
