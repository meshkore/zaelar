// ============================================================================
// test_a_voiced_reply_always_reaches_the_wall.mjs — V2-850, node 4.357.
//
// Measured on a cloud session (2026-11-04): he typed «send Raquel a message, ask her how it's going» twice.
// Both times the engine produced a reply, the voice said it and the spoken record came back — and the chat
// wall stayed EMPTY. He read it as the agent ignoring him. Two shapes, each enough on its own:
//
//   1. The wait filler («a ver…») opens the utterance and the reply streams INTO it, so the turn's only
//      `bot_speech speaking` arrives BEFORE the reply is owed. The owed line then waited for a start that
//      had already happened.
//   2. After the reply event the turn said one more sentence (the verdict's line: «Eso sí: no le he enviado
//      nada…»). The spoken record was therefore LONGER than the owed line, the wall read «not a prefix» as
//      «a cancelled line» and muted it.
//
// The rule kept (V2-752): a line the voice never began is never written. The rule added: a line whose
// voice is already sounding is written at once, and a spoken record that EXTENDS the owed line is written
// whole — a spoken record is proof it sounded.
//
// Run: node tests/browser/unit/chat/test_a_voiced_reply_always_reaches_the_wall.mjs
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
export const reset = () => { msgs = []; _pendingVoiced = null; noteVoiceIdle(); };
export const agentRows = () => msgs.filter(m => m.role === "agent").map(m => m.text);
`;
const S = await import("data:text/javascript," + encodeURIComponent(shim));

const T = "T6·2a8b";
const REPLY = "…ya lo tienes redactado en la tarjeta de mensajería. Míralo y dime si lo envío.";
const TAIL = " Eso sí: no le he enviado nada a nadie, no ha salido ningún mensaje.";

// ── 1 · the filler opened the utterance: the reply is written when it is owed ─────────────────────────────
S.reset();
S.noteVoiceStarted(T);                                   // «a ver…» — before the reply exists
S.pushAgentChat(REPLY, { voiced: true, trace: T });
assert.deepEqual(S.agentRows(), [REPLY], "the voice was already saying this turn: its line is written now");
S.pushAgentChat(REPLY + TAIL, { spoken: true, trace: T });
assert.deepEqual(S.agentRows(), [REPLY + TAIL], "…and the spoken record, with its tail, replaces it in place");

// another turn's sounding voice never paints this line, and an idle voice paints nothing
S.reset();
S.noteVoiceStarted("T5·53b6");
S.pushAgentChat(REPLY, { voiced: true, trace: T });
assert.deepEqual(S.agentRows(), [], "somebody else's utterance does not write this line");
S.reset();
S.noteVoiceStarted(T); S.noteVoiceIdle();
S.pushAgentChat(REPLY, { voiced: true, trace: T });
assert.deepEqual(S.agentRows(), [], "a voice that already went idle is not this line's start");

// ── 2 · no start seen at all: the spoken record that EXTENDS the line writes it ───────────────────────────
S.reset();
S.pushAgentChat(REPLY, { voiced: true, trace: T });
S.pushAgentChat(REPLY + TAIL, { spoken: true, trace: T });
assert.deepEqual(S.agentRows(), [REPLY + TAIL],
  "a spoken record longer than the owed line is that line plus the verdict's sentence — written, never muted");

// the same in English, untraced build
S.reset();
S.pushAgentChat("Drafted it on the messages card.", { voiced: true });
S.pushAgentChat("Drafted it on the messages card. Nothing has been sent yet.", { spoken: true });
assert.deepEqual(S.agentRows(), ["Drafted it on the messages card. Nothing has been sent yet."]);

// ── 3 · the kept rule: a cancelled line is still never written ─────────────────────────────────────────────
S.reset();
S.pushAgentChat(REPLY, { voiced: true, trace: T });
S.dropUnspokenLine(T);
S.pushAgentChat(REPLY + TAIL, { spoken: true, trace: T });
assert.deepEqual(S.agentRows(), [], "a turn cut before it sounded stays off the wall (V2-752)");

console.log("ok — a voiced reply always reaches the wall");
