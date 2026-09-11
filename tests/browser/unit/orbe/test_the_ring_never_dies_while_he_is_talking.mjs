// ============================================================================
// test_the_ring_never_dies_while_he_is_talking.mjs — V2-661b, node 4.156.
//
// THE OPERATOR'S REPORT (2026-09-11, session 63681d60): «he visto que el orbe se ponía de naranja a gris en
// medio de mi conversación, y al cabo de un segundo se volvía a activar solo y se volvía a poner naranja, y
// luego se volvía a desactivar — pero yo no he dejado de hablar en ningún momento».
//
// THE MEASUREMENT, from his own observability:
//   09:11:55.5  👂 dirigido a zaelar          → the client re-armed the ring for a WINDOW (5 s)
//   …           he kept talking: interims every second, NOT ONE vad edge, NOT ONE verdict
//   09:12:00.5  (nothing happened)            → the 5 s timer expired: RING GREY, mid-sentence
//   09:12:08.9  👂 dirigido a zaelar          → orange again
// V2-661 had made the `vad` branch HOLD the ring while his voice is active — and then the very next DIRECTED
// verdict SHORTENED that hold back to a 5 s window. The hold was real and something else undid it.
//
// This MOUNTS the real `sse.js` handler over the real `store.js` with a controllable clock and replays those
// verdicts: a source test would say the branch exists, not that the ring survives the sentence.
//
// Run: node tests/browser/unit/orbe/test_the_ring_never_dies_while_he_is_talking.mjs
// ============================================================================
import assert from "node:assert/strict";

// ── a clock the test drives (store.js arms its ring with setTimeout) ────────────────────────────────────────
let now = 0, seq = 0, timers = [];
globalThis.setTimeout = (fn, ms) => { const t = { fn, at: now + ms, id: ++seq }; timers.push(t); return t.id; };
globalThis.clearTimeout = (id) => { timers = timers.filter(t => t.id !== id); };
const advance = (secs) => {
  now += secs * 1000;
  for (const t of [...timers].sort((a, b) => a.at - b.at)) {
    if (t.at <= now) { timers = timers.filter(x => x !== t); t.fn(); }
  }
};

const mem = new Map([["hb_lang", "es"], ["hb_i18n_es", JSON.stringify({})]]);
globalThis.localStorage = { getItem: k => (mem.has(k) ? mem.get(k) : null),
                            setItem: (k, v) => mem.set(k, String(v)), removeItem: k => mem.delete(k) };
globalThis.fetch = async () => ({ ok: true, json: async () => ({}), text: async () => "" });
globalThis.document = { documentElement: { lang: "es", setAttribute(){}, style: { setProperty(){} } },
                        querySelectorAll: () => [], querySelector: () => null, addEventListener(){},
                        createElement: () => ({ style: {}, classList: { add(){}, remove(){} },
                                                appendChild(){}, setAttribute(){} }),
                        head: { appendChild(){} }, body: { appendChild(){} } };
globalThis.window = { addEventListener(){}, location: { href: "http://localhost/" } };
let sink = null;
globalThis.EventSource = class { constructor() { sink = this; } };

const store = await import("../../../../frontend/app/core/store.js?v=2");
const { openSSE } = await import("../../../../frontend/app/services/sse.js?v=2");
const desktop = { show(){}, close(){}, closeAll(){}, refreshData(){}, createWidget(){}, modifyWidget(){},
                  onDeleted(){}, showConfirm(){}, hideConfirm(){}, move(){}, resize(){}, fullscreen(){},
                  refreshRegistry(){} };
openSSE(desktop);
assert.ok(sink && typeof sink.onmessage === "function", "the SSE handler did not mount");
const push = (o) => sink.onmessage({ data: JSON.stringify(o) });
const lit = () => store.attentionHit();

const voiceOn  = () => push({ kind: "vad", label: "🎤 voz detectada (VAD)", edge: "on" });
const voiceOff = () => push({ kind: "vad", label: "… fin de voz", edge: "off" });
const directed = () => push({ kind: "ambient", label: "👂 dirigido a zaelar", directed: true,
                              window_open: true, window_s: 5.0 });
const ambient  = (open) => push({ kind: "ambient", label: "🙉 ambiente", directed: false,
                                  window_open: open, window_s: 5.0, text: "" });

// ── 1. his session, replayed: the ring must not die inside the monologue ────────────────────────────────────
voiceOn(); directed();
assert.ok(lit(), "the ring must light on the first directed verdict");
advance(7);                       // he keeps talking: fragments finalize, no vad edge
directed();
advance(13.4);                    // the measured gap between 09:11:55.5 and 09:12:08.9, still talking
assert.ok(lit(), "THE BUG: the ring went grey mid-sentence while his voice was still active");
directed();
advance(20);
assert.ok(lit(), "an active voice holds the ring for as long as the engine would");

// ── 2. …and it DOES expire once he really stops ─────────────────────────────────────────────────────────────
voiceOff();
advance(4);
assert.ok(lit(), "four seconds of silence is inside the window — still his");
advance(2);
assert.ok(!lit(), "six seconds of real silence must darken the ring (his own rule)");

// ── 3. a ring already off is never lit by his voice alone ───────────────────────────────────────────────────
voiceOn();
assert.ok(!lit(), "speaking does not GRANT attention — only the gate does (V2-655)");
voiceOff();

// ── 4. the engine saying «the window is closed» beats an active voice (the honest grey) ─────────────────────
// Measured the same session, 09:12:48.3: after a 27 s reply he waited 8.6 s and started talking without the
// name — the engine really had discarded it, and the ring must SAY so until he says the name.
directed(); voiceOn();
assert.ok(lit());
ambient(false);
assert.ok(!lit(), "an engine-closed window darkens the ring even mid-utterance — that grey is honest");
directed();
assert.ok(lit(), "…and the wake word brings it straight back");

// ── 5. zaelar's own reply holds the ring, and does not shorten it on the way in ─────────────────────────────
voiceOff(); directed();
push({ kind: "bot_speech", label: "speaking", speaking: true });
advance(27);                      // the measured length of its reply
assert.ok(lit(), "the ring must survive a long reply (V2-655)");
push({ kind: "bot_speech", label: "idle", speaking: false });
advance(6);
assert.ok(!lit(), "and expire a window after its last word");

console.log("ok — the ring follows his voice, not a timer that nobody refreshes");
