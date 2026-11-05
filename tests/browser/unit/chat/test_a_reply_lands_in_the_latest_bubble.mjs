// ============================================================================
// test_a_reply_lands_in_the_latest_bubble.mjs — V2-852 T13, node 4.372.
//
// Measured in the operator's session (2026-11-05, his ERROR 6): «you are answering me in the middle of your own reply
// and there is text below it — there is one focus, always write in the last message». The voice was queued: a reply
// owed at one moment was spoken two minutes later, after a proactive notice and another turn's line. An utterance that
// named NO turn (the notice's) was taken as this line's start, so the reply was painted under the notice and then,
// when the other turn's late line arrived, crawled in a bubble ABOVE it.
//
// The rules: a line is placed when ITS voice starts it (its trace, its caption or its spoken record) — append by
// arrival, one focus; a spoken record joins the row of its own turn wherever it is, and never moves a row.
//
// Run: node tests/browser/unit/chat/test_a_reply_lands_in_the_latest_bubble.mjs
// ============================================================================
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "../../../..");
const store = readFileSync(path.join(root, "frontend/app/core/store.js"), "utf8");
const i = store.indexOf("const _CHAT_MARKERS");
const j = store.indexOf("// Convenience helpers used across services");
assert.ok(i > 0 && j > i, "the chat-wall slice was not found in store.js — was it renamed?");
const shim = `
let msgs = [];
let _capSeq = 0;
const setChatMsgs = (fn) => { msgs = fn(msgs); };
const _capChat = (xs) => xs;
const createSignal = (v) => { let _v = v; return [() => _v, (n) => { _v = n; }]; };
${store.slice(i, j)}
export const reset = () => { msgs = []; _pendingVoiced = null; _voiceSounding = null; _setVoicedLine(null); };
export const caption = (text, final) => { _capSeq++; noteSpokenAloud(text, final); };
export const agentRows = () => msgs.filter(m => m.role === "agent").map(m => m.text);
export const crawl = () => voicedLine();
`;
const S = await import("data:text/javascript," + encodeURIComponent(shim));


const CASES = [
  { lang: "en", A: "Checking… it shouldn't have asked, and it won't again — I'm telling it to go on.",
    B: "Yep — one search, but two cards: one is a leftover from the cancelled run.",
    note: "🔔 The search has been running for a while.", ask: "Task 3 needs your OK to click «Clear filters». Shall I?" },
  { lang: "es", A: "Lo miro… no tenía que preguntarte y no lo volverá a hacer: le digo que siga.",
    B: "Sí: una búsqueda y dos tarjetas, una es lo que quedó del intento cancelado.",
    note: "🔔 La búsqueda lleva un rato en marcha.", ask: "La tarea necesita tu permiso para pulsar «Borrar filtros». ¿Lo hago?" },
];
const TA = "T29·88e9", TB = "T27·e2da";

for (const c of CASES) {
  S.reset();
  S.pushAgentChat(c.B, { voiced: true, trace: TB });        // owed, its voice queued behind another line
  S.pushAgentChat(c.A, { voiced: true, trace: TA });        // the next reply: B was never started, so it is not on screen
  S.pushAgentChat(c.note);                                  // a proactive notice, written at once
  S.pushAgentChat(c.ask, { spoken: true });                 // the voice says a notice — its record names no turn
  S.noteVoiceStarted("");                                   // …the next utterance starts, naming no turn
  assert.deepEqual(S.agentRows(), [c.note, c.ask],
    `[${c.lang}] an utterance that names no turn is not this reply's start: nothing is written above what comes next`);
  S.pushAgentChat(c.B, { spoken: true, trace: TB });        // it was B the voice was saying
  S.noteVoiceStarted("");
  S.caption(c.A.slice(0, 20), false);                       // and now A, by its own caption
  assert.deepEqual(S.agentRows(), [c.note, c.ask, c.B, c.A], `[${c.lang}] every line lands in the order it was said`);
  assert.equal(S.crawl().trace, TA, `[${c.lang}] the line being said is the latest bubble — one focus`);
  S.pushAgentChat(c.A, { spoken: true, trace: TA });
  assert.deepEqual(S.agentRows(), [c.note, c.ask, c.B, c.A], `[${c.lang}] its record joins its own row`);

  // its own start paints it at once (V2-752 kept), and a late record of an OLDER line updates that row in place
  S.reset();
  S.pushAgentChat(c.B, { voiced: true, trace: TB });
  S.noteVoiceStarted(TB);
  S.caption(c.B.slice(0, 12), false);
  S.pushAgentChat(c.A, { voiced: true, trace: TA });
  S.noteVoiceStarted(TA);
  assert.deepEqual(S.agentRows(), [c.B.slice(0, 12) + "…", c.A]);
  S.pushAgentChat(c.B, { spoken: true, trace: TB });
  assert.deepEqual(S.agentRows(), [c.B, c.A], `[${c.lang}] the trace groups a record with its row, it never reorders`);

  // an untraced build keeps painting on the start it has (nothing names a turn on either side)
  S.reset();
  S.pushAgentChat(c.A, { voiced: true });
  S.noteVoiceStarted("");
  assert.deepEqual(S.agentRows(), [c.A]);
}

console.log("ok — a reply lands in the latest bubble");
