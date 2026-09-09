// V2-647 — the room's conversation is not the operator's chat.
//
// Measured live 2026-09-09 23:18 (operator report, with the screenshot): the mic is always open, the
// attention gate correctly judged EVERY line of a conversation he was having with somebody else as «no
// dirigido a zaelar» and answered all of them with silence — and every one of those lines still landed in
// his chat wall as if he had said it («Pobretito, mi tío», «con los narcos vigilándole»…). The gate's
// verdict is a separate event that arrives just AFTER the transcript, so the wall painted first and learned
// second, and never unlearned. The canvas fast-path had the same hole, and that half is worse: room speech
// carrying «cierra» could close his widgets — precisely what V2-015 exists to prevent.
//
// These drive the REAL module (`attention_hold.js`), never a copy of its logic.
import assert from "node:assert/strict";
import { createAttentionHold } from "../../../../frontend/app/services/attention_hold.js";

function harness(mode = "smart", holdMs = 40) {
  const delivered = [];
  const hold = createAttentionHold({ mode: () => mode, holdMs,
                                     deliver: (text, isFinal) => delivered.push({ text, isFinal }) });
  return { hold, delivered, texts: () => delivered.map(d => d.text) };
}

// ── his own measured session: two fragments of the room's conversation, one ambient verdict ──
{
  const { hold, texts } = harness();
  hold.spoken("Pero", true);
  hold.spoken("este, si es el contable del cartel, está vigilado", true);
  hold.verdict("Pero este, si es el contable del cartel, está vigilado", false);
  assert.deepEqual(texts(), [], "room speech judged ambient must never be delivered (wall OR canvas)");
  assert.equal(hold.pending(), 0, "and must not stay queued either");
}

// ── a turn that WAS for him arrives the same way and must land, whole and instantly ──
{
  const { hold, texts, delivered } = harness();
  hold.spoken("Johnny, ponme la agenda", true);
  hold.verdict("Johnny, ponme la agenda", true);
  assert.deepEqual(texts(), ["Johnny, ponme la agenda"], "a directed turn must be delivered");
  assert.equal(delivered[0].isFinal, true, "and its isFinal must survive the hold — the close fast-path reads it");
}

// ── a fragment the verdict does not cover belongs to a LATER turn: it waits, it is not dropped ──
{
  const { hold, texts } = harness();
  hold.spoken("una cosa de la tele", true);
  hold.spoken("Johnny, abre el reloj", true);
  hold.verdict("una cosa de la tele", false);
  assert.equal(hold.pending(), 1, "an uncovered fragment stays held for its own verdict");
  hold.verdict("Johnny, abre el reloj", true);
  assert.deepEqual(texts(), ["Johnny, abre el reloj"], "and lands when its own verdict says directed");
}

// ── `always` mode has no gate to wait for: nothing is ever held ──
{
  const { hold, texts } = harness("always");
  hold.spoken("lo que sea", true);
  assert.deepEqual(texts(), ["lo que sea"], "in always mode every turn is directed by design");
  assert.equal(hold.pending(), 0);
}

// ── FAIL-OPEN: a verdict that never arrives must not eat his words ──
{
  const { hold, texts } = harness("smart", 30);
  hold.spoken("esto no recibe veredicto", true);
  await new Promise(r => setTimeout(r, 90));
  assert.deepEqual(texts(), ["esto no recibe veredicto"],
    "a missing verdict releases the turn — showing an ambient line is a nuisance, losing a real one is a bug");
}

// ── the wiring: sse.js must actually route both seams through this module ──
{
  const { readFileSync } = await import("node:fs");
  const src = readFileSync(new URL("../../../../frontend/app/services/sse.js", import.meta.url), "utf8");
  assert.ok(src.includes("createAttentionHold("), "sse.js no longer builds the hold");
  assert.ok(src.includes("holdSpokenTurn(desktop, d.text, isFinal)"),
    "spoken transcripts must go through the hold, not straight to the wall");
  assert.ok(src.includes("settleHeldTurns(desktop, d.text || \"\", !!d.directed)"),
    "the gate's verdict must settle what is held");
  assert.ok(!/handleWidgetVoice\(desktop, d\.text, isFinal\);\s*\n\s*\/\/ kind "transcript"/.test(src),
    "the ungated fast-path call must be gone");
}

console.log("ok — the room is not the operator (6 groups)");
