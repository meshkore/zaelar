// V2-747 — the wall prints the agent's line WHILE the voice says it, and stops where the voice stops.
//
// The operator, session 981dd54c (2026-09-21). V2-745 had just made the wall keep only what was actually
// said; he watched that work and asked for the other ORDER:
//
//   «Pones todo el bloque de texto y asumimos que ese bloque ya es el definitivo. Pero ya sabes que si te
//    corto, te corto el output, y realmente tú luego rectificas el audio y solo dejas lo que has llegado a
//    decir… ¿Ese mismo principio de los subtítulos se puede aplicar al chat? ¿Y solo ir mostrando las
//    palabras a medida que las vas diciendo? Y SI YO TE CORTO, TE PARAS EN ESE MOMENTO Y YA NO IMPRIMES MÁS.»
//
//   «¿Podría[s] poner ese texto un poco más grisáceo, más pálido? O el fondo del mensaje en otro color,
//    QUE DESTAQUE, QUE EN ESTE MOMENTO ES LO QUE ESTÁS LEYENDO.»
//
// The channel is LiveKit's audio-synced transcription, the same one V2-745 already wired in and the same
// one the orb's teleprompter has used since V2-116 — so this is a second READER of a proven channel, not
// a new one. What is new is that the wall no longer paints a line before it has sounded.
//
// ⚠️ The GRACE WINDOW is the half that keeps this from being a regression: with no caption channel at all
// (synchronizer off, a transport that never forwards it) an unstreamed line would sit invisible until the
// NEXT reply settled it. This drives the REAL store, so the timer is real and the last group waits on it.
import assert from "node:assert/strict";

const mem = new Map();
globalThis.localStorage = {
  getItem: k => (mem.has(k) ? mem.get(k) : null),
  setItem: (k, v) => mem.set(k, String(v)),
  removeItem: k => mem.delete(k),
};
globalThis.window = { addEventListener() {}, location: { href: "http://127.0.0.1/" } };
globalThis.document = { addEventListener() {}, documentElement: { style: { setProperty() {} } } };

const store = await import("../../../../frontend/app/core/store.js");

const agentLines = () => store.chatMsgs().filter(m => m.role === "agent").map(m => m.text);
const reset = () => { store.setChatMsgs(() => []); store.settleAgentSpoken(); };

const REPLY = "Me alegra que lo veas mejor, y te tomo nota de las dos cosas.";

// ══ 1 · NOTHING IS ON SCREEN BEFORE IT HAS SOUNDED ══════════════════════════════════════════════════
// V2-752 — «before it has sounded» now starts EARLIER than it did here. The line is OWED from the moment
// the model produces it and published only when the engine reports the utterance actually started
// (`bot_speech speaking`), so nothing is on screen and nothing is streamable until then. Measured cost of
// the old shape, session fce3eff3: 9 of 24 replies were painted and never sounded.
reset();
store.pushAgentChat(REPLY, { voiced: true, trace: "T1" });
assert.equal(store.voicedLine(), null, "owed, not yet published: the voice has not begun it");
assert.deepEqual(agentLines(), [], "…and nothing is on the wall either");
store.noteVoiceStarted("T1");
let v = store.voicedLine();
assert.ok(v, "a voiced line must publish what the voice owes, or the wall has nothing to stream");
assert.equal(v.full, REPLY);
assert.equal(v.heard, "", "not one word has sounded yet — «el texto que no has dicho no quiero que exista»");
assert.equal(v.streaming, true);

// ══ 2 · IT GROWS AS THE VOICE SAYS IT ═══════════════════════════════════════════════════════════════
store.pushCaptionSeg("s1", "Me alegra", false);
assert.equal(store.voicedLine().heard, "Me alegra");
store.pushCaptionSeg("s1", "Me alegra que lo veas mejor,", false);
assert.equal(store.voicedLine().heard, "Me alegra que lo veas mejor,",
  "the caption is cumulative and the wall follows it word by word");
assert.equal(store.voicedLine().streaming, true);

// ══ 3 · «SI YO TE CORTO, TE PARAS EN ESE MOMENTO» ═══════════════════════════════════════════════════
// The utterance is cancelled mid-sentence: the caption goes final where the audio stopped.
store.pushCaptionSeg("s1", "Me alegra que lo veas mejor,", true);
assert.equal(store.voicedLine(), null, "settled: the line is no longer being said");
assert.deepEqual(agentLines(), ["Me alegra que lo veas mejor,…"],
  "the history keeps what was HEARD, with the ellipsis that says where it stopped");

// ══ 4 · A LINE THAT SOUNDED WHOLE KEEPS EVERY WORD ══════════════════════════════════════════════════
reset();
store.pushAgentChat(REPLY, { voiced: true, trace: "T4" });
store.pushCaptionSeg("s2", REPLY, true);
assert.equal(store.voicedLine(), null);
assert.deepEqual(agentLines(), [REPLY], "no ellipsis, no trim: it said all of it");

// ══ 5 · A LINE THAT NEVER SOUNDED AT ALL ════════════════════════════════════════════════════════════
// The +157.1 s case: 14.05 s of audio synthesised, `bot_speech` never left idle. The voice then went on
// to say something ELSE, which is the evidence V2-745 requires before removing anything.
// V2-752 — it is now never WRITTEN either, which is the step the operator asked for after watching this
// one work: «vas poniendo de golpe un párrafo… y luego lo borras».
reset();
store.pushAgentChat(REPLY, { voiced: true, trace: "T5" });
store.pushCaptionSeg("s3", "Sí…", true);                 // the next turn's filler — a different line
assert.equal(store.voicedLine(), null, "a caption that is not this line's speech never streams it");
assert.ok(!agentLines().includes(REPLY), "a line the voice never began is not on the wall at all");
store.pushAgentChat("Un segundo.", { voiced: true, trace: "T5b" });    // the next reply settles the owed one
assert.ok(!agentLines().includes(REPLY), "…and settling does not resurrect it");

// ══ 6 · NO CAPTION CHANNEL AT ALL → THE WALL BEHAVES AS IT DID ══════════════════════════════════════
// Silence on a channel is never read as evidence about the voice — the same doctrine as V2-745's removal
// guard. V2-752 replaced the 1200 ms grace window that used to serve this case with `bot_speech speaking`,
// the engine's own statement that the utterance reached the speaker: it does not expire, it does not
// depend on the caption transport, and it is not a guess. The line reaches the wall WHOLE, exactly as it
// did before V2-747 — that has not changed and must not.
reset();
store.pushAgentChat(REPLY, { voiced: true, trace: "T6" });
assert.deepEqual(agentLines(), [], "…but not before the voice has begun it");
store.noteVoiceStarted("T6");
assert.equal(store.voicedLine().streaming, true, "it starts hopeful: the channel may be there");
assert.equal(store.voicedLine().heard, "", "not one caption segment has arrived");
assert.deepEqual(agentLines(), [REPLY], "no segment, and the line is on the wall whole — nothing is lost");

// ══ 7 · A LIVE CHANNEL IS NOT GIVEN UP ON HALFWAY THROUGH A SENTENCE ════════════════════════════════
reset();
store.pushAgentChat(REPLY, { voiced: true, trace: "T7" });
store.pushCaptionSeg("s4", "Me alegra", false);
await new Promise(r => setTimeout(r, 1500));             // longer than the window that used to exist
const after = store.voicedLine();
assert.ok(after && after.streaming === true && after.heard === "Me alegra",
  "a live channel must not be given up on halfway through a sentence");

// ══ 8 · A LINE THAT IS NOT VOICED AT ALL IS NOT STREAMED ════════════════════════════════════════════
// A written reply, a notification, a peer line: there is no voice to follow, so it appears whole at once.
reset();
store.pushAgentChat("🔔 Te recuerdo la cita de las 11:30.", {});
assert.equal(store.voicedLine(), null);
assert.deepEqual(agentLines(), ["🔔 Te recuerdo la cita de las 11:30."]);

// ══ 9 · THE WALL RENDERS `heard`, AND MARKS THE LINE BEING READ ═════════════════════════════════════
// The renderer's half of the contract, read from its source: the two have to agree about WHICH bubble is
// the spoken one and about what goes inside it, and they compare the text to decide.
const fs = await import("node:fs/promises");
const wall = await fs.readFile(new URL("../../../../frontend/app/components/ChatWall.js", import.meta.url), "utf8");
assert.ok(wall.includes("store.voicedLine()"), "the wall must read the line the voice owes");
assert.ok(wall.includes('bubble.classList.add("cw-speaking")'),
  "«que destaque, que en este momento es lo que estás leyendo» — the line being read carries its own mark");
// V2-752 — a line with nothing HEARD yet is drawn WHOLE, not skipped. It is on the wall because the voice
// started it (`bot_speech speaking`), and the caption channel may simply not exist on this build; skipping
// it there left the row invisible until the next reply. What must never be drawn is a line the voice never
// began, and that one is not in `chatMsgs` at all — see node 4.210.
assert.ok(/if \(!say\.heard\) \{/.test(wall),
  "a line already sounding but with no caption yet is shown whole, never skipped");
assert.ok(/h\("div", \{ class: "cw-msg-body" \}, say\.heard\)/.test(wall),
  "it renders what was HEARD, as plain text — a half-said sentence routinely holds an unclosed `*`");
const css = await fs.readFile(new URL("../../../../frontend/app/styles.css", import.meta.url), "utf8");
assert.ok(/\.cw-msg\.agent\.cw-speaking\s*\{/.test(css), "the mark needs a style or it marks nothing");

console.log("ok — the wall says it while it is being said");
