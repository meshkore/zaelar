// ============================================================================
// audio.js — Web Audio analysers + level math. Owns the AudioContext and the two
// AnalyserNodes (mic = person's voice, bot = zaelar's voice). The visualizer and
// the speaker-gate read these; the session service drives init/attach/reset.
// ============================================================================

let ac = null, micAn = null, botAn = null;

export function context() { return ac; }
export function micAnalyser() { return micAn; }
export function botAnalyser() { return botAn; }

// Create the AudioContext + the mic analyser from the live stream. fftSize 2048 → enough for pitch (speaker gate).
export function initMic(stream) {
  ac = new (window.AudioContext || window.webkitAudioContext)();
  micAn = ac.createAnalyser(); micAn.fftSize = 2048;
  ac.createMediaStreamSource(stream).connect(micAn);
  return { ac, micAn };
}

// Attach the bot's returning audio to its own analyser (drives the orb). Best-effort.
export function attachBot(stream) {
  try { botAn = ac.createAnalyser(); botAn.fftSize = 512; ac.createMediaStreamSource(stream).connect(botAn); } catch (_) {}
}

export function reset() { botAn = null; micAn = null; ac = null; }
export function dropBot() { botAn = null; }

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
