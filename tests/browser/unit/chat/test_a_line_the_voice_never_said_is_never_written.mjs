// ============================================================================
// test_a_line_the_voice_never_said_is_never_written.mjs — V2-752, node 4.210.
//
// SESSION fce3eff3 (2026-09-22), measured over its 1401 events: of the 24 replies
// the model generated, **9 were painted on the chat wall and never sounded** —
// 37,5 %. The operator read one of them back at us as evidence:
//
//   «estás soltando chorradas que realmente no estás verbalizando, como por
//    ejemplo, este mensaje de "un momento", si ahora mismo no llevas ningún
//    widget… vas poniendo de golpe un montón de un párrafo lleno de mensajes y
//    luego lo borras. Así no funciona el chat.»
//
// Both halves of that sentence were one mechanism. `pushAgentChat(text, {voiced})`
// wrote the row IMMEDIATELY and a 1200 ms grace window then made it visible whole
// if no caption had arrived; when the utterance had been cancelled before its
// first audio frame no caption ever arrived, so the wall painted a paragraph that
// was never said — and the NEXT reply's `settleAgentSpoken` deleted it. Paint,
// then delete, in front of him.
//
// The replacement is not a longer timer, it is EVIDENCE: `bot_speech speaking` is
// the engine saying this utterance reached the speaker. It carries the turn's
// trace and does not depend on the caption transport, so a build with no
// audio-synced captions still writes the wall (the case the grace window existed
// for) while a cancelled reply writes nothing at all.
//
// The second defect measured in the same session: the spoken record arrives a
// median of 7,3 s and up to 20,8 s after the reply, and `pushAgentChat` only ever
// compared it against the LAST row. Anything he said in between pushed the
// original out of that position, so the late transcript landed as a SECOND bubble
// underneath — «en el chat estás duplicando mensajes, me los estás intercalando
// entre los míos». A line is now identified by its trace, wherever it sits.
//
// Run: node tests/browser/unit/chat/test_a_line_the_voice_never_said_is_never_written.mjs
// ============================================================================
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "../../../..");

// ── the store's wall slice, lifted with the same shim `test_chat_wall_promptness.mjs` uses ────────────
const store = readFileSync(path.join(root, "frontend/app/core/store.js"), "utf8");
const i = store.indexOf("const _CHAT_MARKERS");
const j = store.indexOf("// Convenience helpers used across services");
assert.ok(i > 0 && j > i, "the chat-wall slice was not found in store.js — was it renamed?");

const shim = `
let msgs = [];
// _capSeq counts audio-synced caption segments and lives above the slice; the trim on settle reads it.
// Held at 0 on purpose: this file measures the WRITE rule, and a caption channel that never speaks is the
// conservative case. (No backticks in here — the shim is itself a template literal.)
let _capSeq = 0;
const setChatMsgs = (fn) => { msgs = fn(msgs); };
const _capChat = (xs) => xs;
const createSignal = (v) => { let _v = v; return [() => _v, (n) => { _v = n; }]; };
${store.slice(i, j)}
export const reset = () => { msgs = []; };
export const you = (text) => { msgs = [...msgs, { role: "you", text }]; };
export const dump = () => msgs;
export const agentRows = () => msgs.filter(m => m.role === "agent").map(m => m.text);
`;
const S = await import("data:text/javascript," + encodeURIComponent(shim));

const T1 = "T18·1da8", T2 = "T22·6181";

// ── 1 · A REPLY THE VOICE NEVER BEGAN IS NEVER ON THE WALL ────────────────────────────────────────────
// The measured shape: the model produced «Un momento… Sí, ahora mismo no tienes ningún widget abierto»
// at +323.6 s of that session and `bot_speech` never left idle for it. Nothing about it may reach the
// operator's screen — not for 1200 ms, not for a frame.
S.reset();
S.pushAgentChat("Un momento… ahora mismo no tienes ningún widget abierto", { voiced: true, trace: T1 });
assert.deepEqual(S.agentRows(), [],
  "a line the voice has not started must not be on the wall — this is the 9-in-24 case of session fce3eff3");

// …and when the turn is cut, it disappears without ever having existed.
S.dropUnspokenLine(T1);
assert.deepEqual(S.agentRows(), [], "a cancelled reply leaves nothing behind");

// The late spoken record of that same cancelled turn must not resurrect it either. In the real session
// this arrived up to 20,8 s later, long after he had moved on.
S.pushAgentChat("Un momento…", { spoken: true, trace: T1 });
assert.deepEqual(S.agentRows(), [],
  "the spoken record of a line that was never painted must not create a bubble of its own");

// ── 2 · …AND THE MOMENT THE VOICE STARTS IT, IT IS ─────────────────────────────────────────────────────
S.reset();
S.pushAgentChat("Vale, Paco — misión Apollo 11, NASA, ahora sí.", { voiced: true, trace: T1 });
assert.deepEqual(S.agentRows(), [], "still owed, not written");
S.noteVoiceStarted(T1);
assert.deepEqual(S.agentRows(), ["Vale, Paco — misión Apollo 11, NASA, ahora sí."],
  "`bot_speech speaking` is what writes the line — the evidence that replaced the grace window");

// Another turn's speech never paints this one's owed line.
S.reset();
S.pushAgentChat("primera", { voiced: true, trace: T1 });
S.noteVoiceStarted(T2);
assert.deepEqual(S.agentRows(), [], "somebody else's utterance does not paint this line");

// ── 3 · THE LATE SPOKEN RECORD FINDS ITS ROW WHEREVER IT SITS ─────────────────────────────────────────
// This is the duplication he described. Between the reply and its transcript he said two more things, so
// the agent row was no longer last and the old prefix ladder — which only ever looked at `xs[xs.length-1]`
// — could not see it.
S.reset();
S.pushAgentChat("Sí… te oigo, Paco. Voy con el seis y te lo pongo en el reproductor.", { voiced: true, trace: T1 });
S.noteVoiceStarted(T1);
S.you("Eso no es lo que te acabo de decir.");
S.you("He dicho que vuelvas al inicio del widget de vídeo,");
S.pushAgentChat("Sí… te oigo, Paco. Voy con el seis y te lo pongo en el reproductor.", { spoken: true, trace: T1 });
assert.equal(S.agentRows().length, 1,
  "the spoken record must merge into the row its trace names, not add a second bubble under his lines");
assert.deepEqual(S.dump().map(m => m.role), ["agent", "you", "you"],
  "…and it must not move: the wall is a transcript of the conversation, in the order it happened");

// A barge-in truncates it, and the SHORT one is the true one (V2-745, unchanged — now found by trace).
S.reset();
S.pushAgentChat("Ya… pero es que no me estás diciendo cuál quieres quitar, Paco: en pantalla no hay nada abierto.",
                { voiced: true, trace: T2 });
S.noteVoiceStarted(T2);
S.you("Yo no te he dicho");
S.pushAgentChat("Ya… pero es que no me estás diciendo cuál quieres quitar, Paco:", { spoken: true, trace: T2 });
assert.deepEqual(S.agentRows(), ["Ya… pero es que no me estás diciendo cuál quieres quitar, Paco:…"],
  "a cut line keeps what was heard plus an ellipsis — the honest mark of where the voice stopped");

// ── 4 · THREE REPLIES IN THREE SECONDS: ONLY WHAT SOUNDED SURVIVES ────────────────────────────────────
// Verbatim from the session: +285.9, +289.2 and +291.5 produced three replies while he was complaining.
// Only the third reached the speaker. The first two must leave no trace at all — the old code painted
// them WHOLE (the crawl was the privilege of the last row) and then deleted them.
S.reset();
S.pushAgentChat("Perdona, Paco: «No me estás oyendo» era el vídeo, no una queja.", { voiced: true, trace: "T22" });
S.pushAgentChat("Es que el widget sigue abierto, Paco, no lo he cerrado en ningún momento.", { voiced: true, trace: "T23" });
S.pushAgentChat("Entendido: paro la reproducción y me voy al inicio de la lista, sin cerrar nada.", { voiced: true, trace: "T24" });
S.noteVoiceStarted("T24");
assert.deepEqual(S.agentRows(), ["Entendido: paro la reproducción y me voy al inicio de la lista, sin cerrar nada."],
  "of three replies generated in 3 s, the wall keeps the one the voice actually said");

// ── 5 · THE FALLBACK IS NOT LOST: no caption channel still shows the line ─────────────────────────────
// A build whose transport never forwards audio-synced transcription used to be covered by the 1200 ms
// grace window. `bot_speech` covers it now and covers it BETTER — it is a statement about the voice
// rather than the absence of one. If this ever regressed, every such build would go silent-walled.
S.reset();
S.pushAgentChat("una respuesta entera sin un solo subtítulo", { voiced: true, trace: T1 });
S.noteVoiceStarted(T1);
assert.deepEqual(S.agentRows(), ["una respuesta entera sin un solo subtítulo"],
  "with no caption channel at all the line still reaches the wall — silence on a channel is never " +
  "read as a statement about the voice");

// ── 6 · THE CRAWL IS NOT THE PRIVILEGE OF THE LAST ROW (the render rule, at its seam) ─────────────────
// `i === msgs.length - 1` is exactly why the first two of those three replies rendered whole and at once.
// The renderer is not reachable from here without a DOM, so this pins the predicate where it lives; the
// painted behaviour itself is node 4.211, which is LIVE.
const wall = readFileSync(path.join(root, "frontend/app/components/ChatWall.js"), "utf8");
const k = wall.indexOf("const speaking =");
assert.ok(k > 0, "the `speaking` predicate was not found in ChatWall.js — was it renamed?");
const pred = wall.slice(k, wall.indexOf(";", k));
assert.ok(!/msgs\.length\s*-\s*1/.test(pred),
  "the crawl must not be gated on being the LAST row: that is why three replies inside 3 s rendered the " +
  "first two whole and at once — «en seco pegas un párrafo entero»");
assert.ok(/say\.trace/.test(pred) && /m\.trace/.test(pred),
  "the line being said is identified by the turn's trace, like every other surface since V2-752");

console.log("ok — a line the voice never said is never written (V2-752, node 4.210)");
