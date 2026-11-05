// ============================================================================
// test_a_chat_line_is_never_truncated.mjs — V2-852 T12, node 4.371.
//
// Measured in the operator's session (2026-11-05): the voice said «You're right on both — …» and the wall kept
// «You're right on» (his ERROR 3); «I'll start it now — a wide» was cut by a barge-in and nothing said so. Two shapes:
//   1. The voice stopped mid-sentence (a barge-in, or simply going quiet) and the crawl stayed on screen showing what
//      had been heard so far — a sentence silently shortened, with no mark.
//   2. The next reply settled the line early, cutting it to what had been heard; when the spoken record came back with
//      the WHOLE sentence it was compared with the cut text («…» and all), matched nothing and was thrown away.
//
// The rules: a line cut mid-sentence is marked cut («…»), never silently shortened; the spoken record writes its row
// from what was voiced, compared with what was owed — whole when the voice said it all, marked cut when it stopped.
//
// Run: node tests/browser/unit/chat/test_a_chat_line_is_never_truncated.mjs
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
  { lang: "en", t1: "T24·c533", t2: "T25·61ee",
    line: "You're right on both — that wasn't meant for me, and nothing should have stopped.",
    heard: "You're right on", next: "Noted — that truncation is a real bug." },
  { lang: "es", t1: "T8·41aa", t2: "T9·52bb",
    line: "Tienes razón en las dos cosas: eso no iba conmigo y no debía pararse nada.",
    heard: "Tienes razón en", next: "Anotado: ese corte es un fallo de verdad." },
];

for (const c of CASES) {
  // ── 1 · a barge-in cuts it mid-sentence: the line is marked cut, the crawl does not stay ───────────────────
  S.reset();
  S.pushAgentChat(c.line, { voiced: true, trace: c.t1 });
  S.noteVoiceStarted(c.t1);
  S.caption(c.heard, false);
  assert.equal(S.crawl().heard, c.heard, `[${c.lang}] while it is said, the wall says what was heard`);
  S.dropUnspokenLine("");                                   // `state interrupted`, no trace (as measured)
  assert.equal(S.crawl(), null, `[${c.lang}] the crawl ended: a cut sentence is not left on screen as it stood`);
  assert.deepEqual(S.agentRows(), [c.heard + "…"], `[${c.lang}] cut mid-sentence → marked cut, never silently shortened`);
  // …and when the spoken record comes back with all of it, the row is written whole
  S.pushAgentChat(c.line, { spoken: true, trace: c.t1 });
  assert.deepEqual(S.agentRows(), [c.line], `[${c.lang}] the voice said it all: the spoken record writes it whole`);

  // ── 2 · the next reply settled it early; the record of what was voiced restores it ────────────────────────
  S.reset();
  S.pushAgentChat(c.line, { voiced: true, trace: c.t1 });
  S.noteVoiceStarted(c.t1);
  S.caption(c.heard, false);
  S.pushAgentChat(c.next, { voiced: true, trace: c.t2 });   // settles the first one at what was heard
  assert.deepEqual(S.agentRows(), [c.heard + "…"]);
  S.pushAgentChat(c.line, { spoken: true, trace: c.t1 });
  assert.deepEqual(S.agentRows(), [c.line], `[${c.lang}] an early settle never outlives the record of the voice`);

  // ── 3 · the record itself stops short: written as said, marked cut ────────────────────────────────────────
  S.reset();
  S.pushAgentChat(c.line, { voiced: true, trace: c.t1 });
  S.noteVoiceStarted(c.t1);
  S.pushAgentChat(c.heard, { spoken: true, trace: c.t1 });
  assert.deepEqual(S.agentRows(), [c.heard + "…"], `[${c.lang}] the voice was cut there: the line says so`);

  // ── 4 · the voice goes quiet mid-line: the crawl never stays a shortened sentence ─────────────────────────
  S.reset();
  S.pushAgentChat(c.line, { voiced: true, trace: c.t1 });
  S.noteVoiceStarted(c.t1);
  S.caption(c.heard, false);
  S.noteVoiceIdle();
  assert.equal(S.crawl(), null);
  assert.deepEqual(S.agentRows(), [c.heard + "…"], `[${c.lang}] quiet mid-line → marked cut`);
  // with no caption channel at all, the line it started stays whole
  S.reset();
  S.pushAgentChat(c.line, { voiced: true, trace: c.t1 });
  S.noteVoiceStarted(c.t1);
  S.noteVoiceIdle();
  assert.deepEqual(S.agentRows(), [c.line], `[${c.lang}] a silent caption channel is no statement about the voice`);
}

console.log("ok — a chat line is never truncated");
