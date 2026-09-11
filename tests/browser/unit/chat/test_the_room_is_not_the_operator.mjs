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
import { createAttentionHold, HOLD_MS } from "../../../../frontend/app/services/attention_hold.js";

function harness(mode = "smart", holdMs = 40) {
  const delivered = [];
  const hold = createAttentionHold({ mode: () => mode, holdMs,
                                     deliver: (text, isFinal, judged) => delivered.push({ text, isFinal, judged }) });
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
  const { hold, texts, delivered } = harness("smart", 30);
  hold.spoken("esto no recibe veredicto", true);
  await new Promise(r => setTimeout(r, 90));
  assert.deepEqual(texts(), ["esto no recibe veredicto"],
    "a missing verdict releases the turn — showing an ambient line is a nuisance, losing a real one is a bug");
  // V2-664 — …but it is released UNJUDGED, and `sse.js` gates the canvas fast-path on that flag.
  assert.equal(delivered[0].judged, false,
    "a fail-open release judged nothing: it may reach the wall, never the canvas");
}

// ── V2-664 — his measured session: the fast lane may only act on speech the gate RULED directed ──
// 2026-09-11, session eedf7f9b, 09:40:20-09:40:24. He was describing this very failure out loud («…que ha
// sido poner un vídeo…»); every fragment was correctly judged AMBIENT, and the release beat the verdict by
// 0.36 s. The YouTube card he had closed 32 s earlier reopened on its own, empty.
{
  const { hold, delivered } = harness("smart", 30);
  hold.spoken("Le he dicho que haga una acción, que ha sido", true);
  hold.spoken("poner un vídeo,", true);
  await new Promise(r => setTimeout(r, 90));
  assert.equal(delivered.length, 2, "both fragments still reach the wall — no word is lost");
  assert.ok(delivered.every(d => d.judged === false),
    "none of them may drive the canvas: nobody ruled them directed");
  // and the verdict that finally lands says ambient, which is what actually happened
  hold.verdict("Le he dicho que haga una acción, que ha sido poner un vídeo,", false);
}

// ── a DIRECTED verdict is what licenses the fast lane, and `always` mode IS its own verdict ──
{
  const { hold, delivered } = harness();
  hold.spoken("Johnny, cierra el vídeo", true);
  hold.verdict("Johnny, cierra el vídeo", true);
  assert.equal(delivered[0].judged, true, "a directed verdict licenses the canvas fast-path");
  const b = harness("always");
  b.hold.spoken("cierra el vídeo", true);
  assert.equal(b.delivered[0].judged, true, "in always mode there is no gate: the turn is directed by design");
}

// ── the hold must outlast the gate's own wait — a sentence still being spoken is held «a medias» ──
{
  assert.ok(HOLD_MS >= 5000,
    "a deadline shorter than the accumulator's own wait expires on normal continuous speech: the hold would " +
    "fail open on every long sentence, which is how the canvas got driven by unjudged words");
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
  // V2-664: the delivery must SPLIT — the wall always, the canvas only when judged.
  assert.ok(/deliver:\s*\(text,\s*isFinal,\s*judged\)\s*=>/.test(src),
    "sse.js must receive the verdict flag the hold now hands it");
  assert.ok(/if\s*\(judged\)\s*handleWidgetVoice\(_holdDesk, text, isFinal\);/.test(src),
    "the canvas fast-path must be gated on a real verdict, never on a fail-open release");
  assert.ok(!/handleWidgetVoice\(desktop, d\.text, isFinal\);\s*\n\s*\/\/ kind "transcript"/.test(src),
    "the ungated fast-path call must be gone");
}

console.log("ok — the room is not the operator (9 groups)");
