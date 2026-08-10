// ============================================================================
// audio.js — Web Audio analysers + level math. Owns the AudioContext and the two
// AnalyserNodes (mic = person's voice, bot = zaelar's voice). The visualizer and
// the speaker-gate read these; the session service drives init/attach/reset.
//
// OBSERVABILIDAD DEL CICLO DE VIDA (2026-08-10). Este módulo es el ÚNICO dueño de
// los analizadores, así que es el único sitio donde «se abrió» y «se soltó» son la
// verdad y no una suposición. Antes el log tenía el attach de la pista del bot
// (🔈 TrackSubscribed) pero NUNCA su release, y del micro solo se veía apagarse el
// icono — que es intención, no realidad: un altavoz zombi o un analizador que
// sobrevive a `stop()` no dejaban ni una línea. Se emite SOLO en transición (abrir/
// soltar son operaciones puntuales de la sesión, no de render) y es best-effort.
// ============================================================================
import * as api from "./api.js?v=2";

let ac = null, micAn = null, botAn = null;

export function context() { return ac; }
export function micAnalyser() { return micAn; }
export function botAnalyser() { return botAn; }

// Create the AudioContext + the mic analyser from the live stream. fftSize 2048 → enough for pitch (speaker gate).
export function initMic(stream) {
  // Un `start()` sin `stop()` previo (reconexión) dejaba el AudioContext anterior VIVO y colgado: Chrome corta a
  // ~6 por página, así que unas cuantas reconexiones y `new AudioContext()` empieza a lanzar → el medidor de micro
  // y el orbe se quedan muertos para el resto de la vida de la pestaña. Se cierra el anterior antes de abrir otro.
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

// SOLTAR de verdad: además de olvidar los nodos, se CIERRA el AudioContext (libera el grafo de audio del navegador).
// `reason` dice por qué, que es lo que distingue un cierre normal de una reconexión.
export function reset(reason = "stop") {
  const had = { mic: !!micAn, bot: !!botAn };
  const old = ac;
  botAn = null; micAn = null; ac = null;
  try { if (old && old.state !== "closed" && old.close) old.close(); } catch (_) {}
  if (had.bot) api.uiState("audio:out", { state: "released" });
  if (had.mic) api.uiState("mic:analyser", { state: "closed", reason });
}
export function dropBot() {
  if (!botAn) return;                                    // ya soltada: no hay transición que contar
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
