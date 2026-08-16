// ============================================================================
// feedback-dictation.js — mic-to-text for the feedback textarea (V2-099), browser-native
// (SpeechRecognition / webkitSpeechRecognition), zero backend dependency.
//
// Deliberately NOT the real voice pipeline (LiveKit, services/session-lk.js — a live streaming room,
// wildly disproportionate for "dictate a few sentences into a box") and deliberately NOT
// services/stt.js (an unwired, dead sketch for server-side STT injection — its own header comment
// claims a `ClientSTTInjector` that does not exist anywhere in the Python code; not something to build
// on). No reusable one-shot "transcribe this audio" backend primitive exists today — every STT
// provider is wired into LiveKit's streaming AgentSession — so this stays fully client-side: free,
// no server changes, and it degrades safely where unsupported (mainly Firefox) by simply not being
// available, never by erroring.
// ============================================================================

const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition || null;

export function isSupported() {
  return !!Recognition;
}

/**
 * Starts listening. `onInterim`/`onFinal` receive the recognized text so far; the caller decides how
 * to merge it into the textarea. Returns the recognition handle (pass to `stop()`), or `null` if
 * unsupported.
 */
export function start({ lang = "", onInterim, onFinal, onEnd } = {}) {
  if (!Recognition) return null;
  const rec = new Recognition();
  rec.continuous = true;
  rec.interimResults = true;
  if (lang) rec.lang = lang;
  rec.onresult = (e) => {
    let interim = "", final = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i];
      if (r.isFinal) final += r[0].transcript;
      else interim += r[0].transcript;
    }
    if (final && onFinal) onFinal(final);
    if (interim && onInterim) onInterim(interim);
  };
  rec.onend = () => { if (onEnd) onEnd(); };
  rec.onerror = () => { if (onEnd) onEnd(); };
  try { rec.start(); } catch (_) { return null; }
  return rec;
}

export function stop(rec) {
  try { rec && rec.stop(); } catch (_) {}
}
