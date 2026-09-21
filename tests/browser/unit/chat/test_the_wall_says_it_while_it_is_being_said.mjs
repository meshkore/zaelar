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
reset();
store.pushAgentChat(REPLY, { voiced: true });
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
store.pushAgentChat(REPLY, { voiced: true });
store.pushCaptionSeg("s2", REPLY, true);
assert.equal(store.voicedLine(), null);
assert.deepEqual(agentLines(), [REPLY], "no ellipsis, no trim: it said all of it");

// ══ 5 · A LINE THAT NEVER SOUNDED AT ALL ════════════════════════════════════════════════════════════
// The +157.1 s case: 14.05 s of audio synthesised, `bot_speech` never left idle. The voice then went on
// to say something ELSE, which is the evidence V2-745 requires before removing anything.
reset();
store.pushAgentChat(REPLY, { voiced: true });
store.pushCaptionSeg("s3", "Sí…", true);                 // the next turn's filler — a different line
assert.equal(store.voicedLine().heard, "", "a caption that is not this line's speech never streams it");
store.pushAgentChat("Un segundo.", { voiced: true });    // the next reply settles the owed one
assert.ok(!agentLines().includes(REPLY), "a line the voice never began does not stay written");

// ══ 6 · NO CAPTION CHANNEL AT ALL → THE WALL BEHAVES AS IT DID ══════════════════════════════════════
// Silence on a channel is never read as evidence about the voice — the same doctrine as V2-745's removal
// guard. Without this the line would be invisible until the NEXT reply arrived.
reset();
store.pushAgentChat(REPLY, { voiced: true });
assert.equal(store.voicedLine().streaming, true, "it starts hopeful: the channel may be there");
await new Promise(r => setTimeout(r, 1500));             // longer than the grace window
assert.equal(store.voicedLine().streaming, false,
  "no segment arrived: the wall falls back to showing the whole line, as it did before V2-747");
assert.deepEqual(agentLines(), [REPLY], "…and the stored line is untouched, so nothing was lost");

// ══ 7 · THE GRACE WINDOW IS CANCELLED THE MOMENT THE CHANNEL SPEAKS ═════════════════════════════════
reset();
store.pushAgentChat(REPLY, { voiced: true });
store.pushCaptionSeg("s4", "Me alegra", false);
await new Promise(r => setTimeout(r, 1500));
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
assert.ok(/if \(!say\.heard\) return;/.test(wall),
  "a line with nothing heard yet is not drawn at all");
assert.ok(/h\("div", \{ class: "cw-msg-body" \}, say\.heard\)/.test(wall),
  "it renders what was HEARD, as plain text — a half-said sentence routinely holds an unclosed `*`");
const css = await fs.readFile(new URL("../../../../frontend/app/styles.css", import.meta.url), "utf8");
assert.ok(/\.cw-msg\.agent\.cw-speaking\s*\{/.test(css), "the mark needs a style or it marks nothing");

console.log("ok — the wall says it while it is being said");
