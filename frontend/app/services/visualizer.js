// ============================================================================
// visualizer.js — the single requestAnimationFrame loop. Draws the voice orb
// (zaelar's voice) and the camera spectrum (the person's voice, gated so the
// agent's echo doesn't move it), runs the speaker-gate DSP, drives the mic meter,
// and does the real-time MIC-BLOCKED detection. Imperative by nature; it reads the
// audio analysers + the reactive store and writes back only UI-facing signals.
// ============================================================================
import * as store from "../core/store.js?v=2";
import { micRMS, micAnalyser, botAnalyser, level } from "./audio.js?v=2";
import { t as tr } from "../core/i18n.js?v=1";

let raf = null, orbPhase = 0, vizPhase = 0;
// Was the orb already painted in its resting form after freezing? (avoids repainting it 60 times per second while
// stopped, which kept it rippling: the phase advances inside the drawing itself)
let _orbFrozenAt = false;

// The orb's own glow layers below are translucent by design (additive "lighter" blend, alpha .18-.63) — on a
// canvas cleared to transparent each frame that means whatever sits BEHIND the orb in the page (a widget card)
// shows straight through it, which reads as "part of the widget" instead of a solid shape floating on top
// (operator 2026-07-22, screenshot: the browser widget's text was visible bleeding through the orb's body).
// z-index was never the issue (.orbwrap is already 100000, above every widget/panel except the 3 deliberately
// higher transient overlays — boot/update/settings). Fix: paint an OPAQUE backstop disc (the app's own --canvas
// background color, dark or light) first, so the glow layers composite onto solid color instead of transparency.
let _bgTheme = null, _bgRgb = [10, 15, 22];
function hexRgb(hex) {
  const h = hex.replace("#", "").trim();
  const full = h.length === 3 ? h.split("").map(c => c + c).join("") : h;
  const n = parseInt(full, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function bgRgb() {
  const t = document.documentElement.dataset.theme || "dark";
  if (t !== _bgTheme) {
    _bgTheme = t;
    const v = getComputedStyle(document.documentElement).getPropertyValue("--canvas").trim() || (t === "light" ? "#f7f9fc" : "#0a0f16");
    try { _bgRgb = hexRgb(v); } catch (_) { _bgRgb = t === "light" ? [247, 249, 252] : [10, 15, 22]; }
  }
  return _bgRgb;
}

// PRO radial spectrum (ported from prototype_interviewer), driven by the PERSON's voice.
function drawOrbPro(x, W, H, buf, lvl) {
  const cx = W / 2, cy = H / 2, R = Math.min(W, H) * 0.34;
  vizPhase += 0.005 + lvl * 0.05;
  const N = 72, layers = [["#2DD4BF", "#1FAE9C", 0, 1], ["#4D8DFF", "#3D6FE0", 2.1, .85], ["#9A8CFF", "#6A5CFF", 4.2, .7]];
  // Opaque backstop FIRST — but soft-edged (radial gradient, alpha 1→0) + a drop shadow, not a flat hard-edged
  // disc: a plain solid circle read as a "hole punched in the widget behind it" rather than a shape floating
  // ABOVE it (operator 2026-07-22, 2nd pass: "it does not feel like it is above everything"). The shadow is
  // the depth cue that actually sells "this is on top, casting a shadow down" — a flat fill has no such cue.
  x.save();
  x.globalCompositeOperation = "source-over"; x.globalAlpha = 1;
  x.shadowColor = "rgba(0,0,0,.45)"; x.shadowBlur = 24; x.shadowOffsetY = 5;
  const [br, bg2, bb] = bgRgb();
  const backstop = x.createRadialGradient(cx, cy, R * 0.7, cx, cy, R * 1.15);
  backstop.addColorStop(0, `rgba(${br},${bg2},${bb},1)`);
  backstop.addColorStop(1, `rgba(${br},${bg2},${bb},0)`);
  x.beginPath(); x.arc(cx, cy, R * 1.15, 0, 7); x.fillStyle = backstop; x.fill();
  x.restore();
  x.globalCompositeOperation = "lighter";
  layers.forEach(L => {
    x.beginPath();
    for (let i = 0; i <= N; i++) {
      const a = i / N * Math.PI * 2;
      const fb = buf ? buf[Math.floor((i % N) * buf.length / (N * 1.6))] / 255 : 0;
      const wob = Math.sin(a * 3 + vizPhase + L[2]) * 0.05 + Math.sin(a * 5 - vizPhase * 1.4) * 0.035;
      const r = R * (0.74 + wob + fb * 0.5 * L[3] + lvl * 0.2);
      const px = cx + Math.cos(a) * r, py = cy + Math.sin(a) * r; i ? x.lineTo(px, py) : x.moveTo(px, py);
    }
    x.closePath();
    const g = x.createLinearGradient(cx - R, cy - R, cx + R, cy + R); g.addColorStop(0, L[0]); g.addColorStop(1, L[1]);
    x.globalAlpha = 0.18 + lvl * 0.45; x.fillStyle = g; x.fill();
    x.globalAlpha = 0.55; x.lineWidth = 1.6; x.strokeStyle = L[0]; x.stroke();
  });
  x.globalCompositeOperation = "source-over"; x.globalAlpha = 1;
  x.beginPath(); x.arc(cx, cy, R * 0.30, 0, 7); x.fillStyle = "rgba(255,255,255," + (0.05 + lvl * 0.3) + ")"; x.fill();
}

// FRIENDLY soft circle — KEPT (isolated control), switch with window.zaelar.orb('friendly').
function drawOrbFriendly(x, W, H, buf, lvl) {
  const cx = W / 2, cy = H / 2, base = Math.min(W, H) * 0.24;
  orbPhase += 0.03; const r = base * (1 + lvl * 0.7) + Math.sin(orbPhase) * 2;
  const g = x.createRadialGradient(cx, cy, r * 0.2, cx, cy, r * 1.7);
  g.addColorStop(0, "rgba(61,111,224,0.8)"); g.addColorStop(1, "rgba(61,111,224,0.04)");
  x.fillStyle = g; x.beginPath(); x.arc(cx, cy, r * 1.7, 0, 7); x.fill();
  x.fillStyle = (store.started() ? "#3D6FE0" : "#c2ccda"); x.beginPath(); x.arc(cx, cy, r, 0, 7); x.fill();
  x.fillStyle = "#fff"; x.globalAlpha = .9; x.beginPath(); x.arc(cx - r * 0.25, cy - r * 0.25, r * 0.22, 0, 7); x.fill(); x.globalAlpha = 1;
}

// audit.silent is shared with the session (auditMicCapture sets it; the loop clears it when sound returns).
export function startVisualizer({ orbCanvas, vizCanvas, getStream, getGate, audit }) {
  cancelAnimationFrame(raf);
  function draw() {
    const gate = getGate && getGate();
    if (gate && gate.enabled) gate.update();   // only run the (heavy) speaker-gate DSP when it's actually enabled

    // MIC METER: true RMS of the captured mic. If flat while you talk, the browser is capturing silence (wrong
    // device / OS mute) — the problem is BEFORE the network, not STT.
    //
    // GATED BY AGENT STATE (2026-08-10). Previously it ALWAYS wrote whenever an analyser existed —
    // and the analyser SURVIVES `stop()` (nothing calls `audio.reset()`), so with the agent stopped the meter
    // kept publishing a level and the VU meter kept moving: the operator saw «microphone capturing» in
    // observability and assumed someone was listening. With the agent stopped there is no mic: the level is
    // 0 and this is reported ONCE (not every frame, so effects are not awakened 60 times per second).
    const live = store.agentLive();
    const micAn = live ? micAnalyser() : null;
    if (micAn) { const r = micRMS(); store.setMicLevel(r); if (r > 0.02) audit.silent = false; }
    else if (store.micLevel() !== 0) store.setMicLevel(0);

    // MIC BLOCKED check (real-time): the OS muted our track or another app (SuperWhisper) grabbed the mic → 🚫 ring.
    // Stopped is not «blocked»: when powering off, REMOVE the 🚫 instead of leaving it stuck at the last value.
    if (!live) {
      if (store.micBlocked().show) store.setMicBlocked({ show: false, msg: "" });
    } else if (store.started()) {
      const stream = getStream(); const t = stream && stream.getAudioTracks()[0];
      const muted = !!(t && (t.muted || t.readyState === "ended"));
      const micMuted = store.micMuted();
      // if I muted it MYSELF (micMuted), it is not a block: the mic icon indicates that, not the 🚫
      const show = !micMuted && (muted || audit.silent);
      store.setMicBlocked({
        show,
        msg: muted ? tr("viz.mic_in_use")
           : (audit.silent ? tr("viz.mic_silent") : ""),
      });
    }

    const dpr = devicePixelRatio || 1;
    // ORB = the AGENT's voice — exactly like the interviewer spectrum (moves when zaelar speaks)
    let bbuf = null, blvl = 0; const botAn = botAnalyser();
    if (botAn) { bbuf = new Uint8Array(botAn.frequencyBinCount); botAn.getByteFrequencyData(bbuf); blvl = level(botAn); }
    const oc = orbCanvas, W = oc.clientWidth, H = oc.clientHeight;
    // With the agent STOPPED the orb is drawn ONCE and stays still: `frozen` (styles.css) dims its color, and
    // skipping redraw also freezes its ripple (the phase advances inside drawOrb*). A gray orb that
    // keeps moving would still say «I am here». Paint the first frame after the change so it remains in its
    // resting form, not halfway through its last gesture.
    const frozen = !live;
    if (W && !(frozen && _orbFrozenAt)) {
      if (oc.width !== W * dpr) { oc.width = W * dpr; oc.height = H * dpr; }
      const x = oc.getContext("2d"); x.setTransform(dpr, 0, 0, dpr, 0, 0); x.clearRect(0, 0, W, H);
      (store.orbStyle() === "friendly" ? drawOrbFriendly : drawOrbPro)(x, W, H, frozen ? null : bbuf, frozen ? 0 : blvl);
    }
    // Only LATCH the frozen state on a frame that could actually draw. `W` is 0 whenever the orb has no laid-out
    // box — which the mobile dock produces as a NORMAL state, because with the agent stopped its centre slot hides
    // the orb (display:none) and shows a ⏻ instead. Recording "already frozen" on those frames meant the latch was
    // still set when the orb came back, so `frozen && _orbFrozenAt` stayed true and it never repainted: measured on
    // the stopped -> ⏻ -> starting path, 0 painted pixels with the canvas never even resized (2026-08-18).
    // The desktop never hid its orb, so it never hit this.
    if (W) _orbFrozenAt = frozen;
    // SPECTRUM under the camera = the PERSON's voice (mic), gated so the agent's echo doesn't move it. `vizCanvas`
    // lives inside CameraUnit, which the operator can hide (2026-08-09: hidden by default) — null is a real,
    // permanent state now, not a startup race, so this whole block is skipped rather than crashing `draw()` (which
    // ran SYNCHRONOUSLY from main.js before `ensureVoice()` — a null-deref here used to abort boot entirely,
    // leaving "Encendiendo zaelar…" stuck forever since the code that lifts the boot veil never got to run).
    let mbuf = null;
    if (micAn && !store.botSpeaking()) { mbuf = new Uint8Array(micAn.frequencyBinCount); micAn.getByteFrequencyData(mbuf); }
    const vc = vizCanvas, w = vc ? vc.clientWidth : 0, hh = vc ? vc.clientHeight : 0;
    if (vc && w) {
      if (vc.width !== w * dpr) { vc.width = w * dpr; vc.height = hh * dpr; }
      const x = vc.getContext("2d"); x.setTransform(dpr, 0, 0, dpr, 0, 0); x.clearRect(0, 0, w, hh);
      const N = 42, bw = w / N; x.fillStyle = "rgba(61,111,224,.6)";
      if (mbuf) for (let i = 0; i < N; i++) { const v = mbuf[Math.floor(i * mbuf.length / N)] / 255; const bh = Math.max(2, v * hh * 0.95); x.fillRect(i * bw + 1, hh - bh, bw - 2, bh); }
    }
    raf = requestAnimationFrame(draw);
  }
  draw();
}

export function stopVisualizer() { cancelAnimationFrame(raf); }
