// ============================================================================
// mic.js — THE microphone switch (V2-654). ONE door: every writer of the mic
// state goes through here, and one write moves ALL FOUR things at once.
//
// WHAT BROKE (measured 2026-09-10, session 85eec898). The state lived in
// `store.micMuted` + localStorage and had SIX writers. Four of them —
// `main.js`'s boot probe, the ⏻ power button on both shells, and
// `DockBar.js` — set the signal and localStorage directly and NEVER called
// `applyMic()`. So the 🎤 icon read CLOSED while the published track kept
// sending: the engine transcribed the operator for seven minutes and escalated
// an errand off what it heard. Nothing could catch it, because the engine had
// no notion of a microphone switch at all.
//
// Operator's ruling, verbatim: «cuando yo desactivo el icono, ese estado es
// total … el estado se debe controlar en un solo sitio y controla todo el
// sistema. No puede fallar nunca.»
//
// THE FOUR THINGS ONE WRITE MOVES:
//   1. the SIGNAL   → `store.micMuted` (what the icon draws)
//   2. the MEMORY   → localStorage `hb_mic_muted` (survives a reload)
//   3. the AUDIO    → the live capture track + the LiveKit publication
//   4. the ENGINE   → `POST /api/mic`, so the turn gate can refuse to act on
//                     audio the operator never authorised (voice/mic_input.py)
//
// A door nobody can be asked to REMEMBER: `tests/browser/unit/mic/` fails if
// any file outside this one writes `setMicMuted`, `hb_mic_muted` or reaches
// for the audio track. The rule that each caller has to remember is not a rule
// — the same doctrine that closed the control-plane credential holes.
//
// The transport (3) is injected rather than imported: `session.js` and
// `session-lk.js` are two different engines and each owns its own room/stream,
// and importing either from here would be a cycle (both import this module).
// Until one registers, a write still moves 1, 2 and 4 — the ENGINE gate alone
// already makes a muted state effective, which is the point of putting it
// server-side.
// ============================================================================
import * as store from "../core/store.js?v=2";
import * as api from "./api.js?v=2";

let _transport = null;   // (muted:boolean) => void — installed by the live session engine
let _lastSent = null;    // last value the engine was told; null = never told

// The session engine calls this on start so the door can reach the live track.
// Registering APPLIES immediately: a freshly published track must be born in
// the state the icon is already showing (the reconnect hole — the icon said
// closed, the new publication came up open).
export function useTransport(fn) {
  _transport = typeof fn === "function" ? fn : null;
  if (_transport) applyNow("transport-attached");
}

export function muted() { return store.micMuted(); }

// The ONE write. `reason` is not decoration: it travels to the engine and lands
// in the timeline, so «who closed this mic» is answerable — power button, boot
// probe, the operator's own click or the heartbeat re-asserting.
export function setMuted(next, reason = "ui") {
  const want = !!next;
  store.setMicMuted(want);
  try { localStorage.setItem("hb_mic_muted", want ? "1" : "0"); } catch (_) {}
  applyNow(reason);
}

export function toggle(reason = "ui") { setMuted(!store.micMuted(), reason); return store.micMuted(); }

// Re-assert the CURRENT state over audio + engine, without changing it. Called
// on connect, on track publish, and free of charge on every heartbeat — this is
// what makes the switch self-correcting instead of a one-shot command that can
// be lost by a reconnect, a republished track or a request that never landed.
export function applyNow(reason = "assert") {
  const want = store.micMuted();
  if (_transport) { try { _transport(want); } catch (_) {} }
  if (want === _lastSent) return;
  // Remember what LANDED, never what we tried: a request lost before a heartbeat
  // exists behind it (⏻ off, no room) would otherwise be recorded as told and
  // never re-sent — the silent divergence in miniature.
  try {
    api.micState(want, reason).then((ok) => { if (ok && store.micMuted() === want) _lastSent = want; });
  } catch (_) {}
}

// The value the session heartbeat piggybacks (~4s). Sending it EVERY beat, not
// only on change, is deliberate: a beat is the cheapest correction channel we
// have, and it heals a divergence the client cannot even detect — an engine
// restarted underneath a live tab comes back with its switch at the boot
// default and nobody would ever tell it otherwise.
export function beat() {
  const want = store.micMuted();
  _lastSent = want;
  return want;
}
