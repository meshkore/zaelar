// ============================================================================
// audio.js — Web Audio analysers + level math. Owns the AudioContext and the two
// AnalyserNodes (mic = person's voice, bot = zaelar's voice). The visualizer and
// the speaker-gate read these; the session service drives init/attach/reset.
//
// LIFECYCLE OBSERVABILITY (2026-08-10). This module is the ONLY owner of the analysers,
// so it is the only place where “attached” and “released” are truth rather than an
// assumption. The log used to record the bot track attach (🔈 TrackSubscribed) but
// NEVER its release, while for the mic it only showed the icon turning off—intent,
// not reality: a zombie speaker or an analyser surviving `stop()` left no trace.
// Emit ONLY on transitions (attach/release are discrete session operations, not render)
// and best-effort.
// ============================================================================
import * as api from "./api.js?v=2";

let ac = null, micAn = null, botAn = null;

export function context() { return ac; }
export function micAnalyser() { return micAn; }
export function botAnalyser() { return botAn; }

// Create the AudioContext + the mic analyser from the live stream. fftSize 2048 → enough for pitch (speaker gate).
export function initMic(stream) {
  // Without this, a null `stream` — the session was stopped mid-startup — surfaced as "Failed to execute
  // 'createMediaStreamSource': parameter 1 is not of type 'MediaStream'": a browser message that mentions neither
  // the session, nor ⏻, nor the stop, and that cost an operator a whole session read backwards. The error is still
  // thrown (there is no continuing from here), but it now says what actually happened.
  if (!(stream instanceof MediaStream)) {
    throw new Error("audio.initMic: no MediaStream — the voice session was stopped while starting up "
                    + `(received: ${stream === null ? "null" : typeof stream})`);
  }
  // A `start()` without a previous `stop()` (reconnection) left the previous AudioContext ALIVE and hanging:
  // Chrome caps pages at ~6, so a few reconnections made `new AudioContext()` throw → the mic meter and orb stayed
  // dead for the rest of the tab's lifetime. Close the previous one before opening another.
  if (ac) reset("reinit");
  ac = new (window.AudioContext || window.webkitAudioContext)();
  micAn = ac.createAnalyser(); micAn.fftSize = 2048;
  ac.createMediaStreamSource(stream).connect(micAn);
  api.uiState("mic:analyser", { state: "open", reason: "session_start" });
  return { ac, micAn };
}

// Attach the bot's returning audio to its own analyser (drives the orb). Best-effort.
export function attachBot(stream) {
  try {
    botAn = ac.createAnalyser(); botAn.fftSize = 512; ac.createMediaStreamSource(stream).connect(botAn);
    api.uiState("audio:out", { state: "attached" });
  } catch (_) {}
}

// Truly RELEASE: besides forgetting the nodes, CLOSE the AudioContext (releasing the browser's audio graph).
// `reason` says why, distinguishing a normal close from a reconnection.
export function reset(reason = "stop") {
  const had = { mic: !!micAn, bot: !!botAn };
  const old = ac;
  botAn = null; micAn = null; ac = null;
  try { if (old && old.state !== "closed" && old.close) old.close(); } catch (_) {}
  if (had.bot) api.uiState("audio:out", { state: "released" });
  if (had.mic) api.uiState("mic:analyser", { state: "closed", reason });
}
export function dropBot() {
  if (!botAn) return;                                    // already released: no transition to record
  botAn = null;
  api.uiState("audio:out", { state: "released" });
}

// Average frequency magnitude (0..1) — used for orb/spectrum intensity.
export function level(an) {
  if (!an) return 0;
  const b = new Uint8Array(an.frequencyBinCount); an.getByteFrequencyData(b);
  let s = 0; for (let i = 0; i < b.length; i++) s += b[i]; return s / b.length / 255;
}

// True time-domain RMS of the mic (0..1-ish) — the on-screen "are you actually being heard" meter.
export function micRMS() {
  if (!micAn) return 0;
  const b = new Uint8Array(micAn.fftSize); micAn.getByteTimeDomainData(b);
  let s = 0; for (let i = 0; i < b.length; i++) { const v = (b[i] - 128) / 128; s += v * v; } return Math.sqrt(s / b.length);
}
