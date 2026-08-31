// THE CHAT WALL MUST NOT ARRIVE LATE (V2-116, session b403c979 from 2026-08-18).
//
// Operator report: “the agent is talking to me, it does not appear in the subtitles, the text does not appear in the chat
// for its response … the response has taken more than a minute from when I heard it by voice until you put it
// on the chat wall”.
//
// Measured in that session’s durable log: the response is GENERATED and rendered on the wall when the
// LiveKit `transcript` arrives, which is not emitted until the conversation item closes—in other words, until TTS
// has finished speaking the ENTIRE response:
//     reply 12:32:13.844 → transcript 12:32:19.267   (5,4 s)
//     reply 12:33:11.376 → transcript 12:33:23.611   (12,2 s)
// The fix pushes the text to the wall as soon as the model generates it, and merges the subsequent `transcript` by
// PREFIX. This tests the pure component where it can fail on its own: `pushAgentChat` deduplication.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "../../../..");

// ── 1) the seam: sse.js pushes the response to the wall on the `reply` event, without waiting for the transcript ──────────
const sse = readFileSync(path.join(root, "frontend/app/services/sse.js"), "utf8");
const replyBranch = sse.slice(sse.indexOf('/reply/.test'), sse.indexOf('/reply/.test') + 1400);
assert.ok(replyBranch.includes("pushAgentChat"),
  "the FlashBrain `reply` branch must push the text to the wall NOW; otherwise, the wall depends again on " +
  "TTS finishing speaking (5-12 s measured)");
assert.ok(/d\.role === "assistant"/.test(replyBranch),
  "…y solo la del asistente (un `reply` sin role de asistente no es texto que el agente haya dicho)");
// and the SUBTITLES remain synchronized with the audio, not this
assert.ok(!replyBranch.includes("captionSeg"),
  "the subtitles are NOT fed from here: they are synchronized with the audio (session-lk.js)");

// ── 2) pushAgentChat prefix deduplication, excerpted from the store (same technique as test_energy_scale.mjs) ────
const store = readFileSync(path.join(root, "frontend/app/core/store.js"), "utf8");
const i = store.indexOf("const _CHAT_MARKERS");
const j = store.indexOf("// Convenience helpers used across services");
assert.ok(i > 0 && j > i, "pushAgentChat not found in store.js—was it renamed?");

// reactive dependencies are replaced with a plain array: what is tested is the merge RULE
const shim = `
let msgs = [];
const setChatMsgs = (fn) => { msgs = fn(msgs); };
const _capChat = (xs) => xs;
${store.slice(i, j)}
export const reset = () => { msgs = []; };
export const push = (role, text) => { msgs = [...msgs, { role, text }]; };
export const dump = () => msgs;
`;
const mod = await import("data:text/javascript," + encodeURIComponent(shim));

// (a) the REAL case: it is rendered on generation, and the identical transcript arriving 12 s later does NOT duplicate
mod.reset();
const reply = "Según los resultados, el lanzamiento más destacado de Ferrari en 2026 es el Ferrari F80.";
mod.pushAgentChat(reply);
mod.pushAgentChat(reply);
assert.equal(mod.dump().length, 1, "el transcript posterior no puede duplicar la burbuja");

// (b) barge-in: the transcript arrives TRUNCATED → the complete text is preserved, not two bubbles
mod.reset();
mod.pushAgentChat(reply);
mod.pushAgentChat("Según los resultados, el lanzamiento");
assert.equal(mod.dump().length, 1, "una locución cortada no puede dejar dos burbujas");
assert.equal(mod.dump()[0].text, reply, "gana el texto COMPLETO (lo que el agente quiso decir)");

// (c) the reverse: a fragment arrives first and then the full text → it is EXPANDED in place
mod.reset();
mod.pushAgentChat("Según los resultados");
mod.pushAgentChat(reply);
assert.equal(mod.dump().length, 1);
assert.equal(mod.dump()[0].text, reply, "el texto entero sustituye al parcial ya pintado");

// (d) the waiting filler (💬, V2-114) does NOT merge with the response: they are two genuinely spoken things
mod.reset();
mod.pushAgentChat("💬 Espera…");
mod.pushAgentChat(reply);
assert.equal(mod.dump().length, 2, "el relleno y la respuesta son burbujas distintas");

// (e) two different responses remain two
mod.reset();
mod.pushAgentChat("Son las tres.");
mod.pushAgentChat("Ya te he puesto la música.");
assert.equal(mod.dump().length, 2);

// (f) the 🔔 notify marker continues to be normalized (previous behavior, not broken)
mod.reset();
mod.pushAgentChat("He creado el widget «X».");
mod.pushAgentChat("🔔 He creado el widget «X».");
assert.equal(mod.dump().length, 1, "🔔 sigue fundiéndose con el mismo texto sin marcador");

console.log("chat wall promptness: OK");
