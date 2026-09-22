// V2-749 — THE CHEAP EAR: the browser hears the name for free, and the paid tap only opens when it does.
//
// THE MEASUREMENT. Session 48394dd0 (2026-09-22), `stt_provider=deepgram`, `attention_mode=smart` — the
// 🤖 wake-word mode ON. Every utterance in the room was still published, transcribed and billed before the
// gate threw it away: «Me llamo Paco.» transcribed three times, «Vale, vamos a centrarnos en arreglar»
// transcribed and discarded. The operator:
//
//   «si yo lo tengo todo el día escuchando como si fuera un Alexa, pues me va a consumir la energía, los
//    créditos y en realidad no lo vamos a llegar a utilizar ni una sola vez. Entonces, esa detección del
//    nombre tiene que funcionar obviamente escuchando el micrófono en background, pero se tiene que hacer
//    a nivel de navegador.»
//
//   «si yo digo "muéstrame el tiempo Johnny"… lo que no puede ser es que el sistema empiece a escuchar a
//    partir de la palabra clave en adelante, porque le he dicho unas cuantas palabras antes que son
//    relevantes y que generan una mejor experiencia de usuario que la que se tiene con Alexa.»
//
// ⚠️ THE GROUP THAT MATTERS MOST IS THE LAST ONE. Parking the microphone over an ear that is not actually
// listening is an agent that cannot hear at all — a worse failure than any bill, and one that would look
// like a dead product rather than a bug. `armed()` is the licence, and it is only granted by the
// recogniser's OWN `onstart`.
import assert from "node:assert/strict";

// A recogniser under our control: the real one is the browser's, and everything this module promises is
// about WHEN it is trusted, so the lifecycle has to be drivable.
class FakeSR {
  constructor() { FakeSR.last = this; this.started = false; }
  start() { this.started = true; queueMicrotask(() => this.onstart && this.onstart()); }
  stop() { this.started = false; if (this.onend) this.onend(); }
  // drive: one FINAL result
  say(text) { this.onresult && this.onresult({ resultIndex: 0, results: [Object.assign([{ transcript: text }], { isFinal: true })] }); }
  partial(text) { this.onresult && this.onresult({ resultIndex: 0, results: [Object.assign([{ transcript: text }], { isFinal: false })] }); }
  fail(error) { this.onerror && this.onerror({ error }); }
}
globalThis.window = { SpeechRecognition: FakeSR };

const wake = await import("../../../../frontend/app/services/wakeword.js");
const tick = () => new Promise(r => setTimeout(r, 0));

// ══ 1 · THE NAME IS WHATEVER HE RENAMED IT TO, AND «zaelar» KEEPS WORKING ════════════════════════════
// V2-747: he renames the assistant by voice, mid-session. A spotter with the word compiled in would stop
// working the moment he does — which is the whole reason this is a general recogniser and not a keyword
// model. Additive exactly like `attention._wakewords()`.
assert.deepEqual(wake.wakeNames("Johnny"), ["zaelar", "johnny"]);
assert.deepEqual(wake.wakeNames(""), ["zaelar"], "no rename yet — the default still answers");
assert.deepEqual(wake.wakeNames("Zaelar"), ["zaelar"], "never the same word twice");

// ══ 2 · THE MATCH IS THE ENGINE'S MATCH ══════════════════════════════════════════════════════════════
// `voice/attention.py::_norm` strips accents and lowercases; if this side did not, «Iñaki» and «Inaki»
// would be two different wake words and only the engine's half would honour both.
assert.equal(wake.normalize("Iñaki Á"), "inaki a");
assert.ok(wake.spotIn("oye Johnny, ponme música", ["johnny"]));
assert.ok(wake.spotIn("JOHNNY", ["johnny"]), "case is not a signal");
assert.ok(wake.spotIn("oye Iñaki, abre la agenda", ["Inaki"]),
  "de-accented on BOTH sides — the name he typed and the name the recogniser writes rarely agree on tildes");

// …and never a substring. A short nickname inside another word would open the tap on half the sentences
// in the room — the failure mode that makes a wake word useless rather than merely wrong.
assert.equal(wake.spotIn("es un zaelariano convencido", ["zaelar"]), null);
assert.equal(wake.spotIn("hablando de johnnys", ["johnny"]), null);
assert.equal(wake.spotIn("cualquier cosa", []), null, "no names = no spot, never a crash");

// ══ 3 · THE WORDS BEFORE THE NAME TRAVEL WITH IT ═════════════════════════════════════════════════════
wake._reset();
let spots = [];
wake.install({ getNames: () => ["johnny"], onSpot: s => spots.push(s) });

wake.offer("Ostras, para la música");            // no name → held, for free
assert.deepEqual(spots, [], "a sentence without the name never reaches the engine — that is the saving");
wake.offer("Johnny");
assert.equal(spots.length, 1);
assert.equal(spots[0].text, "Johnny", "the utterance that carried the name, verbatim");
assert.equal(spots[0].before, "Ostras, para la música",
  "«le he dicho unas cuantas palabras antes que son relevantes»");

// The whole sentence in one breath is the same mechanism with an empty tail: the name is inside `text`,
// so the engine's gate rules it directed and there is nothing to reclaim.
spots = [];
wake.offer("muéstrame el tiempo Johnny");
assert.equal(spots[0].text, "muéstrame el tiempo Johnny");
assert.equal(spots[0].before, "");

// ══ 4 · A TAIL FEEDS ONE TURN AND ONLY ONE ═══════════════════════════════════════════════════════════
// Two copies of a sentence read as a stutter, and the engine's own `reclaim_ambient_tail` makes the same
// promise on its side — a disagreement here would show up as the first half of an order arriving twice.
wake._reset();
spots = [];
wake.install({ getNames: () => ["johnny"], onSpot: s => spots.push(s) });
wake.offer("para la música");
wake.offer("Johnny");
wake.offer("Johnny otra vez");
assert.equal(spots[1].before, "", "the tail was consumed by the first turn");

// …and it expires. A sentence from half a minute ago is not the front of this one.
wake._reset();
spots = [];
wake.install({ getNames: () => ["johnny"], onSpot: s => spots.push(s) });
const t0 = Date.now();
wake.offer("esto es de hace rato", { now: t0 });
wake.offer("Johnny", { now: t0 + (wake.PREROLL_S + 5) * 1000 });
assert.equal(spots[0].before, "", `nothing older than ${wake.PREROLL_S}s reaches the turn`);

// ══ 5 · THE WALL STAYS CLEAN WHILE THE AGENT IS PARKED ═══════════════════════════════════════════════
// «veo que intenta en el chat, va escribiendo el texto y luego lo borra… ese texto jamás debe aparecer
// ahí». The predicate `sse.js` reads, driven here rather than copied.
assert.equal(wake.paintsProvisional("always", false), true, "in `always` every turn is directed — it paints");
assert.equal(wake.paintsProvisional("smart", false), false, "cold in wake-word mode: write nothing");
assert.equal(wake.paintsProvisional("wakeword", false), false);
assert.equal(wake.paintsProvisional("smart", true), true, "the ring is lit — his name was heard, so it writes");

// ══ 6 · ⚠️ THE PARK LICENCE IS THE RECOGNISER'S OWN «I AM RUNNING» ═══════════════════════════════════
wake._reset();
assert.equal(wake.armed(), false, "nothing installed, nothing running: never park");
assert.equal(wake.start(), false, "no deps = no ear");

wake._reset();
const armedLog = [];
wake.install({ getNames: () => ["johnny"], onSpot: () => {}, onArmed: (ok, why) => armedLog.push([ok, why]) });
assert.equal(wake.armed(), false, "installed is not running");
assert.equal(wake.start(), true);
assert.equal(wake.armed(), false, "…and start() is not onstart(): the browser has not confirmed anything yet");
await tick();
assert.equal(wake.armed(), true, "now, and only now, the tap may close");
assert.deepEqual(armedLog.at(-1), [true, "started"],
  "the arming PUSHES its own news: `armed()` is not a signal, so nothing is subscribed to it and an effect " +
  "that only polled it would park a beat late or never");

// An interim result is never a spot: the recogniser revises them as the sentence grows, and a name heard
// in a fragment it then rewrites would open the tap on a word that was never said.
spots = [];
wake.install({ getNames: () => ["johnny"], onSpot: s => spots.push(s) });
FakeSR.last.partial("Johnny");
assert.deepEqual(spots, [], "interim results are guesses");
FakeSR.last.say("Johnny, abre la agenda");
assert.equal(spots.length, 1);

// A FATAL error disarms for good. Permission refused or no capture device has no recovery, and pretending
// otherwise leaves the tap parked over an ear that is not there.
FakeSR.last.fail("not-allowed");
assert.equal(wake.armed(), false, "denied: unpark and stay unparked");
assert.equal(wake.start(), false, "and never try again this session");

// A TRANSIENT end is not the same thing: it disarms (so the tap opens — a gap is cheaper than deafness)
// and it rearms on its own.
wake._reset();
wake.install({ getNames: () => ["johnny"], onSpot: () => {} });
wake.start();
await tick();
assert.equal(wake.armed(), true);
FakeSR.last.stop();
assert.equal(wake.armed(), false, "while it is down the agent hears EVERYTHING, which is the safe side");

// stop() is final and leaves nothing behind for the next session to read.
wake.stop();
assert.equal(wake.armed(), false);

// ══ 7 · A BROWSER WITHOUT THE API CHANGES NOTHING AT ALL ═════════════════════════════════════════════
// Firefox, an old Safari, a locked-down install. The mode must behave exactly as it did before this
// module existed — never park, never claim an ear.
wake._reset();
const saved = globalThis.window;
globalThis.window = {};
assert.equal(wake.supported(), false);
wake.install({ getNames: () => ["johnny"], onSpot: () => {} });
assert.equal(wake.start(), false);
assert.equal(wake.armed(), false, "no ear, no licence, no parking — the whole feature is inert");
globalThis.window = saved;

console.log("ok — the cheap ear spots the name");
