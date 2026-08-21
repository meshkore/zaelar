// ============================================================================
// test_a_send_that_fails_says_so.mjs — V2-256, node 4.33.
//
// THE FAILURE THIS EXISTS FOR, measured on a live engine on 2026-08-21:
//
//     POST /api/feedback  ->  {"ok":false,"error":"send_failed","status":401}
//     GET  /api/feedback  ->  {"ok":false,"items":[]}
//
// …and the panel showed NOTHING. No error, no thanks, the text still sitting in the box. `send()` was
// `if (res && res.ok) { … }` with no `else`, and the Sent tab rendered "Nothing sent yet" for a list
// it could not reach — which is not a smaller truth, it is a different and wrong one.
//
// Two properties, and they are tested at two levels ON PURPOSE:
//
//   1. THE DECISION (below): the module that reads the API answer must produce a visible outcome for
//      a failure, must carry the fact the transport already knew, and must not confuse "empty" with
//      "unreachable". Pure, no DOM, runs in the deterministic suite every time.
//   2. THE WIRING (below): both surfaces must ROUTE through that module. A decision module nothing
//      calls is the V2-199 failure — a test that proves the code compiles. Guarded from the SOURCE,
//      because a green decision test is exactly what a dead call site would leave behind.
//
// The third level — that the line is really PAINTED — is node 4.34, which renders in Chromium. It has
// to be separate: this file could pass forever while the element sat in the DOM with zero pixels, and
// that specific way of shipping nothing has already happened once here (V2-124's detached canvas) and
// once in this very file's component (see the eager-ternary check at the end).
//
// Run: node tests/browser/unit/feedback/test_a_send_that_fails_says_so.mjs
// ============================================================================
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ENGINE = join(HERE, "..", "..", "..", "..");
const read = (...p) => readFileSync(join(ENGINE, ...p), "utf8");

const { sendOutcome, listOutcome, lineFor } = await import(
  "../../../../frontend/app/services/feedback-state.js?v=1");

// --- 1. the decision --------------------------------------------------------------------------

// The exact body the engine returned to the operator. This is the case the product got wrong.
const refused = sendOutcome({ ok: false, error: "send_failed", status: 401 });
assert.equal(refused.ok, false);
assert.equal(refused.key, "feedback.sendError", "a refused send has to resolve to a VISIBLE sentence");
assert.equal(refused.detail, "401",
  "the status was already in hand and got dropped — '(401)' is the difference between a day and a minute");

const ok = sendOutcome({ ok: true, id: "abc", status: "received" });
assert.equal(ok.ok, true);
assert.equal(ok.key, "feedback.thanks");
assert.equal(ok.detail, "", "nothing went wrong, so there is no fact to append");

// A `status` field on a SUCCESS body means the item's status ('received'), not an HTTP code. Reading
// it as a failure detail would print "(received)" next to a thank-you.
assert.equal(sendOutcome({ ok: true, status: "received" }).detail, "");

// The browser-side catch in feedback-api.js has no status to offer. Say the sentence, invent nothing.
assert.equal(sendOutcome({ ok: false, error: "send_failed" }).detail, "");
assert.equal(sendOutcome(null).ok, false, "no answer at all is still a failure, not a silence");
assert.equal(sendOutcome(undefined).key, "feedback.sendError");

// A named error is worth showing; the generic one every failure carries is not.
assert.equal(sendOutcome({ ok: false, error: "empty_message" }).detail, "empty_message");
assert.equal(sendOutcome({ ok: false, error: "rate_limited" }).detail, "rate_limited");

// --- 2. empty is not the same as unreachable ---------------------------------------------------

const reachableEmpty = listOutcome({ ok: true, items: [] });
assert.equal(reachableEmpty.reachable, true);
assert.equal(reachableEmpty.emptyKey, "feedback.emptyState");

const unreachable = listOutcome({ ok: false, items: [] });
assert.equal(unreachable.reachable, false);
assert.notEqual(unreachable.emptyKey, "feedback.emptyState",
  "'Nothing sent yet' for a list we cannot reach tells the user their reports were never sent");
assert.equal(unreachable.emptyKey, "feedback.listUnavailable");

assert.deepEqual(listOutcome({ ok: true, items: [{ id: "1" }] }).items, [{ id: "1" }]);
assert.deepEqual(listOutcome({ ok: true, items: "not-an-array" }).items, [],
  "a malformed body must degrade to an empty list, never throw inside a render");
assert.deepEqual(listOutcome(null).items, []);
assert.equal(listOutcome(null).reachable, false);

// --- 3. the visible line -----------------------------------------------------------------------

const t = (k) => ({ "feedback.sendError": "No se ha podido enviar.", "feedback.thanks": "Gracias." })[k] || k;
assert.equal(lineFor(refused, t), "No se ha podido enviar. (401)");
assert.equal(lineFor(ok, t), "Gracias.");
assert.ok(lineFor(refused, t).trim().length > 0, "an empty line is the bug this file is about");

// --- 4. both surfaces route through it (the wiring, not the compile) ----------------------------

const SURFACES = [
  ["frontend/app/components/FeedbackWidget.js", read("frontend", "app", "components", "FeedbackWidget.js")],
  ["frontend/mobile/app/shell/MenuSheet.js", read("frontend", "mobile", "app", "shell", "MenuSheet.js")],
];

for (const [name, src] of SURFACES) {
  assert.ok(/from\s+"[^"]*feedback-state\.js/.test(src),
    `${name} does not import the shared reading — that is how the desktop ended up without a failure branch`);
  assert.ok(/sendOutcome\s*\(/.test(src), `${name} never calls sendOutcome()`);
  // The shape that shipped: a success-only branch with nothing after it.
  assert.ok(!/if\s*\(\s*r(?:es)?\s*&&\s*r(?:es)?\.ok\s*\)/.test(src),
    `${name} still reads \`.ok\` by hand instead of through the shared reading`);
}

const WIDGET = SURFACES[0][1];
assert.ok(/listOutcome\s*\(/.test(WIDGET), "the desktop panel must read the LIST answer too, not just the send");
assert.ok(/feedback\.listUnavailable/.test(WIDGET) || /emptyKey/.test(WIDGET),
  "the Sent tab still has only one empty state");

// --- 5. the eager ternary that made the SUCCESS state invisible too -----------------------------
//
// `justSent() ? h(...) : null` as a child is evaluated ONCE while the panel is being built. It read
// `false`, appended nothing, and no later setJustSent(true) could put a node there — so the thank-you
// had never appeared either, silently, with no error anywhere. In this hyperscript a reactive child
// MUST be a function (dom.js::appendChildren), which is the same lesson as V2-124's detached canvas.
// Checked here and not only in the renderer because the renderer is a `live` node: it does not run
// on an ordinary suite, and this trap is one keystroke away at all times.
for (const [name, src] of SURFACES) {
  // The shape of the bug, precisely: a call sitting ALONE at the start of a line with the `?` on the
  // next one — which in this file is only ever an argument to h(), i.e. a child. An inline ternary
  // (`cond() ? a : b` mid-line) is the normal way to build a class string INSIDE an arrow and is not
  // what broke. This does not catch every possible eager read; it catches the one that shipped, and
  // node 4.34 catches the general case by looking at pixels.
  const offenders = [...src.matchAll(/\n[ \t]*([A-Za-z_$][\w$.]*\(\))[ \t]*\r?\n[ \t]*\?/g)]
    .map((m) => `${m[1]} ? …`);
  assert.deepEqual(offenders, [],
    `${name}: a signal read as a bare child — evaluated ONCE while the tree is built, never re-rendered, ` +
    "no error anywhere. Wrap it: `() => (cond() ? a : b)`");
}

console.log("ok");
