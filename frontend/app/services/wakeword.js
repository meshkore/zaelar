// ============================================================================
// wakeword.js — THE CHEAP EAR (V2-749).
//
// WHAT WAS WRONG. The 🤖 wake-word mode never changed what the microphone COST.
// Audio was published continuously, Deepgram transcribed every word of it, and
// `voice/attention.py` then decided — after the fact, on text we had already
// paid for — that the turn was not addressed to us. Measured 2026-09-22
// (session 48394dd0, `stt_provider=deepgram`): «Me llamo Paco.» transcribed
// three times and discarded twice, «Vale, vamos a centrarnos en arreglar»
// transcribed and discarded, the mode reading `smart` throughout. The operator:
//
//   «si yo lo tengo todo el día escuchando como si fuera un Alexa, pues me va a
//    consumir la energía, los créditos y en realidad no lo vamos a llegar a
//    utilizar ni una sola vez. Entonces, esa detección del nombre tiene que
//    funcionar obviamente escuchando el micrófono en background, pero se tiene
//    que hacer a nivel de navegador.»
//
// WHAT THIS DOES. While the agent is cold in a wake-word mode, the published
// track is PARKED (no audio leaves the browser, so nothing is transcribed and
// nothing is billed) and a recogniser that runs inside the browser and costs us
// nothing listens for the assistant's own name. When it hears it, the tap opens
// and the sentence the browser already has is handed to the engine.
//
// WHY THE BROWSER'S Web Speech API AND NOT A KEYWORD MODEL. The name is not
// ours to choose: the operator renames the assistant by voice, mid-session, to
// anything he likes (`memory/slots.py::assistant.name`, V2-747). Every trained
// spotter — Porcupine and friends — needs the keyword compiled in advance, so
// a rename would silently stop working, which is the exact failure V2-747 was
// about. A general recogniser matches whatever the name happens to be TODAY.
// It is free of OUR tokens, which is the cost the operator is paying.
//
// THE WORDS BEFORE THE NAME ARE THE POINT. An Alexa hears you from the wake
// word onwards; he asked for the opposite, in as many words: «si yo digo
// "muéstrame el tiempo Johnny"… lo que no puede ser es que el sistema empiece a
// escuchar a partir de la palabra clave en adelante, porque le he dicho unas
// cuantas palabras antes que son relevantes». The recogniser is already holding
// them for free, so the spot carries the WHOLE utterance, and anything said in
// the seconds before it travels as `before` → `attention.note_preroll()` →
// reclaimed by the wake-word turn immediately behind it. That reclaim mechanism
// is not new (`reclaim_ambient_tail`, 10 s): this only feeds it from a cheaper
// source.
//
// THE ONE FAILURE THAT MATTERS IS DEAFNESS. A parked tap over a spotter that is
// not actually running is an agent that cannot hear at all — worse than any
// bill. So parking is not a mode, it is a CONSEQUENCE of the spotter being
// demonstrably alive: `armed()` only answers true after the recogniser's own
// `onstart` fired, and any error that is not transient disarms it for the rest
// of the session. Disarmed, this module changes nothing whatsoever and the
// engine behaves exactly as it did before it existed.
//
// Dependency-free matching on purpose (the V2-647 lesson): `normalize` and
// `spotIn` are the production rules, and the test drives THEM, not a copy.
// ============================================================================

// How far back a sentence may reach for the words that preceded the name. The
// same 10 s `voice/attention.py::reclaim_ambient_tail` uses — they are two ends
// of one mechanism and a difference between them would show up as a sentence
// arriving half-reclaimed.
export const PREROLL_S = 10;

// ⚠️ THE SPOT LIVES ON THE INTERIM STREAM, AND THAT IS NOT A DETAIL.
// The first build only believed a FINAL result — the safe choice against a
// fragment the recogniser later rewrites. But Chrome only finalises when you
// STOP TALKING. Measured 2026-09-22 (session 5789bad4): the operator kept
// speaking, and his five «Johnny»s arrived as ONE final **33.5 s after the
// session started**. His words: «he estado diciendo la palabra Johnny mucho
// tiempo y la primera vez le ha costado mucho… si dicen Johnny cuatro veces
// después de darle el botón de Start y no funciona se van a preocupar.» The
// latency of a finals-only spot is not a number; it is «however long he talks».
//
// So the two concerns are split rather than traded. The INTERIM opens the tap
// and the window — cheap, reversible, and a false one costs a few seconds of
// STT, never a wrong action. The FINAL is only a BACKSTOP, for the case the
// spot alone leaves silent: he said the name and nothing else, so the paid STT,
// which came up mid-word, has nothing to answer.
const _MAX_TAIL = 4;             // same bound as the server's tail: 4 entries
const _RESTART_MS = 400;         // the recogniser stops by itself constantly (silence); this is the rearm
// …and this is how long its absence is FORGIVEN before the tap is told. A continuous recogniser ends and
// restarts on its own every few seconds of quiet; reporting each of those as «the ear is down» would
// unpark and re-park the microphone on that same rhythm — audio flapping, a paid stream opening and
// closing for nothing, and a timeline of noise that hides the one outage that matters. The cost of the
// grace is bounded and stated: a name said inside a restart gap can be missed, once, and he says it again.
const _GRACE_MS = 1500;
const _FATAL = new Set(["not-allowed", "service-not-allowed", "audio-capture"]);

// Lowercase, accent-free — byte-for-byte the rule `voice/attention.py::_norm`
// applies, so a name that matches here matches there. Without the NFD pass
// «Iñaki» and «Inaki» are two different wake words and only one of them works.
export function normalize(text) {
  return String(text || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
}

// The names this ear answers to: whatever he renamed it to, plus "zaelar",
// which keeps working after a rename (habit, or a stray «oye zaelar» from
// before it) — additive exactly like `attention._wakewords()`.
export function wakeNames(assistantName) {
  const out = ["zaelar"];
  const n = normalize(assistantName).trim();
  if (n && n !== "zaelar") out.push(n);
  return out;
}

// Whole-word match, never a substring: «zaelar» must not fire on «zaelariano»,
// and a two-letter nickname must not fire on every word that contains it. The
// text is de-accented first, so \b behaves (it is ASCII-only in JS).
export function spotIn(text, names) {
  const n = normalize(text);
  for (const w of (names || [])) {
    const k = normalize(w).trim();
    if (!k) continue;
    if (new RegExp("\\b" + k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\b").test(n)) return k;
  }
  return null;
}

// MAY THE WALL PAINT THE PROVISIONAL LINE OF THE TURN BEING HEARD RIGHT NOW? Lives here, dependency-free
// and beside the rules it belongs with, so `sse.js` reads THIS answer and the test drives the same one
// (the V2-647 lesson again — `services/listening.js` is the precedent).
//
// In `always` every turn is directed: the caption is the whole point and it paints. In a wake-word mode a
// COLD turn is going to be discarded, and painting it writes his sentence on the wall and then rubs it out
// in front of him. `hit` is the ring — lit by the engine's own directed verdicts, the instant wake-word spot
// among them — so the line starts the moment his name is heard and never before.
export function paintsProvisional(mode, hit) {
  return String(mode || "always") === "always" || !!hit;
}

// ── the live ear ────────────────────────────────────────────────────────────
let _rec = null;          // the browser recogniser, while one exists
let _armed = false;       // its `onstart` fired and no fatal error since — the ONLY licence to park
let _dead = false;        // a fatal error: this session never arms again
let _tail = [];           // {at, text} of local utterances that carried no name
let _deps = null;         // injected: { getLang, getNames, onSpot, onArmed, log }
let _restartT = null;
let _wantRunning = false;

export function supported() {
  try { return !!(window.SpeechRecognition || window.webkitSpeechRecognition); } catch (_) { return false; }
}

// The parking licence. Nothing else in the app may decide it is safe to silence
// the microphone — see the deafness note at the top.
export function armed() { return _armed && !_dead; }

function _push(text) {
  const t = String(text || "").trim();
  if (!t) return;
  const now = Date.now();
  _tail = _tail.filter(x => (now - x.at) <= PREROLL_S * 1000).concat([{ at: now, text: t }]).slice(-_MAX_TAIL);
}

// Everything still inside the pre-roll window, oldest first, and CONSUMED: a
// tail that fed one turn must not feed the next (the server's reclaim makes the
// same promise on its own side, and two copies of a sentence read as a stutter).
export function takeTail(now = Date.now()) {
  const keep = _tail.filter(x => (now - x.at) <= PREROLL_S * 1000).map(x => x.text);
  _tail = [];
  return keep.join(" ").trim();
}

let _spotted = false;    // the name already fired for the utterance being spoken RIGHT NOW

function _fire(spot) {
  if (_deps && _deps.onSpot) { try { _deps.onSpot(spot); } catch (_) {} }
  return spot;
}

// A GROWING partial of the utterance he is saying right now. Fires at most once
// per utterance: the recogniser repeats and extends its partials, and a second
// spot would re-open a tap that is already open and re-anchor the window from
// the middle of his sentence.
export function offerInterim(text, { now = Date.now() } = {}) {
  if (_spotted) return null;
  const t = String(text || "").trim();
  if (!t) return null;
  const names = (_deps && _deps.getNames && _deps.getNames()) || [];
  if (!spotIn(t, names)) return null;
  _spotted = true;
  // Everything he has said up to here — earlier utterances still inside the
  // window, plus this partial, which is where the name lives. The paid STT
  // takes over from this instant, so this is the last thing it will not hear.
  const tail = takeTail(now);
  return _fire({ phase: "spot", text: "", before: tail ? tail + " " + t : t });
}

// One finalized local utterance. Exported so the test drives the real decision
// rather than a transcript of it.
export function offer(text, { now = Date.now() } = {}) {
  const t = String(text || "").trim();
  const spotted = _spotted;
  _spotted = false;                       // the utterance is over either way
  if (!t) return null;
  if (spotted) {
    // The tap has been open since the interim. This is the backstop only, and
    // the engine drops it when the paid STT already produced a turn.
    return _fire({ phase: "final", text: t, before: "" });
  }
  const names = (_deps && _deps.getNames && _deps.getNames()) || [];
  if (!spotIn(t, names)) { _push(t); return null; }
  // The name only surfaced when the recogniser settled (a short utterance, or
  // a partial that read as something else): the browser owns this turn whole.
  return _fire({ phase: "final", text: t, before: takeTail(now) });
}

let _graceT = null;

// Both notifiers fire on the TRANSITION only. `onArmed` drives a park and a line in the timeline, and a
// callback that repeats its own state turns both into noise.
function _disarm(why) {
  clearTimeout(_graceT); _graceT = null;
  if (!_armed) return;
  _armed = false;
  if (_deps && _deps.onArmed) { try { _deps.onArmed(false, why); } catch (_) {} }
}

function _arm() {
  clearTimeout(_graceT); _graceT = null;
  if (_armed) return;
  _armed = true;
  if (_deps && _deps.onArmed) { try { _deps.onArmed(true, "started"); } catch (_) {} }
}

export function install(deps) { _deps = deps || null; }

export function start() {
  if (_dead || _wantRunning || !supported() || !_deps) return false;
  _wantRunning = true;
  _spin();
  return true;
}

function _spin() {
  if (_dead || !_wantRunning) return;
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let r;
  try { r = new SR(); } catch (_) { _dead = true; _disarm("construct-failed"); return; }
  r.lang = (_deps.getLang && _deps.getLang()) || "es-ES";
  r.continuous = true;
  r.interimResults = true;           // the spot lives here — see the note above `_MAX_TAIL`
  r.onstart = _arm;
  r.onresult = e => {
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const res = e.results[i];
      const text = (res[0] && res[0].transcript) || "";
      if (res.isFinal) offer(text); else offerInterim(text);
    }
  };
  r.onerror = ev => {
    const err = (ev && ev.error) || "";
    if (_FATAL.has(err)) {
      // Permission refused, no input device, or the browser refusing the
      // service: there is no recovery and pretending otherwise would leave the
      // tap parked over an ear that is not there. Stay unparked, forever.
      _dead = true;
      _wantRunning = false;
      _disarm(err);
      if (_deps.log) { try { _deps.log("wakeword: spotter off (" + err + ")"); } catch (_) {} }
      return;
    }
    // `no-speech` and `aborted` are the normal weather of a continuous
    // recogniser and are not a reason to stop trusting it; `onend` rearms.
  };
  r.onend = () => {
    _rec = null;
    if (!_wantRunning || _dead) { _disarm("ended"); return; }
    // A routine end. Rearm at once and only call it an outage if the rearm does not arrive — see
    // `_GRACE_MS`. An outage that outlives the grace unparks, because a gap is cheaper than deafness.
    clearTimeout(_graceT);
    _graceT = setTimeout(() => _disarm("down"), _GRACE_MS);
    clearTimeout(_restartT);
    _restartT = setTimeout(_spin, _RESTART_MS);
  };
  _rec = r;
  try { r.start(); } catch (_) { _disarm("start-threw"); }
}

export function stop() {
  _wantRunning = false;
  _spotted = false;
  clearTimeout(_restartT); _restartT = null;
  _tail = [];
  _disarm("stopped");
  if (_rec) { try { _rec.onend = null; _rec.stop(); } catch (_) {} _rec = null; }
}

// Test seam: the module holds session state, and a test that cannot clear it
// reads the previous case's tail. Never called by the app.
export function _reset() {
  _rec = null; _armed = false; _dead = false; _tail = []; _deps = null; _spotted = false;
  _wantRunning = false; clearTimeout(_restartT); _restartT = null;
  clearTimeout(_graceT); _graceT = null;
}
