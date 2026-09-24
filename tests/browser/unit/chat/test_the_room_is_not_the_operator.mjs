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

// V2-745 — a release now has TWO halves and the harness keeps them apart, because they answer different
// questions: `delivered` is what the CANVAS fast-path sees (one call per STT fragment, the shape V2-664
// tuned), and `wall` is the one line that reaches the chat (the fragments joined, because one paragraph he
// dictated is one message — see attention_hold.js's own header for the measured session).
function harness(mode = "smart", holdMs = 40) {
  const delivered = [], wall = [];
  const hold = createAttentionHold({
    mode: () => mode, holdMs,
    deliver: (text, isFinal, judged, whole) =>
      (whole ? wall : delivered).push({ text, isFinal, judged }),
  });
  return { hold, delivered, wall, texts: () => delivered.map(d => d.text),
           wallTexts: () => wall.map(d => d.text) };
}

// ── his own measured session: two fragments of the room's conversation, one ambient verdict ──
{
  const { hold, texts, wallTexts } = harness();
  hold.spoken("Pero", true);
  hold.spoken("este, si es el contable del cartel, está vigilado", true);
  hold.verdict("Pero este, si es el contable del cartel, está vigilado", false);
  assert.deepEqual(texts(), [], "room speech judged ambient must never be delivered (wall OR canvas)");
  assert.deepEqual(wallTexts(), [], "…and nothing of it may reach the wall either");
  assert.equal(hold.pending(), 0, "and must not stay queued either");
}

// ── a turn that WAS for him arrives the same way and must land, whole and instantly ──
{
  const { hold, texts, delivered, wallTexts } = harness();
  hold.spoken("Johnny, ponme la agenda", true);
  hold.verdict("Johnny, ponme la agenda", true);
  assert.deepEqual(texts(), ["Johnny, ponme la agenda"], "a directed turn must be delivered");
  assert.deepEqual(wallTexts(), ["Johnny, ponme la agenda"], "…and painted on the wall, once");
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
  const { hold, texts, wallTexts } = harness("always");
  hold.spoken("lo que sea", true);
  assert.deepEqual(texts(), ["lo que sea"], "in always mode every turn is directed by design");
  assert.deepEqual(wallTexts(), ["lo que sea"], "…and it still reaches the wall exactly once");
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
  assert.equal(delivered.length, 2, "both fragments still reach the canvas seam — no word is lost");
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
  // V2-745 adds the second axis: `whole` says which half of the release this call is.
  assert.ok(/deliver:\s*\(text,\s*isFinal,\s*judged,\s*whole\)\s*=>/.test(src),
    "sse.js must receive both flags the hold now hands it");
  assert.ok(/if\s*\(whole\)\s*return void store\.pushChat/.test(src),
    "the JOINED paragraph is the only thing that may reach the wall — one sentence, one bubble");
  assert.ok(/if\s*\(judged\)\s*handleWidgetVoice\(_holdDesk, text, isFinal\);/.test(src),
    "the canvas fast-path must be gated on a real verdict, never on a fail-open release");
  assert.ok(!/handleWidgetVoice\(desktop, d\.text, isFinal\);\s*\n\s*\/\/ kind "transcript"/.test(src),
    "the ungated fast-path call must be gone");
}

// ── V2-763 · THE WALL MAY NOT CONTRADICT THE ORB ─────────────────────────────────────────────────────────
// Session 2ffe9713 (2026-09-24): a 90 s monologue with no wake word, every fragment ruled AMBIENT, zero brain
// turns — and the fail-open painted it as his bubbles under a grey orb, because the gate holds an unfinished
// sentence until it ends (verdict at 415 s for a turn begun at 324 s). With the orb OFF the fail-open waits.
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
function ringHarness(lit, ceilingMs = 10000) {
  const wall = [];
  const settledWhy = [];
  const hold = createAttentionHold({
    mode: () => "smart", holdMs: 30, ceilingMs, listening: () => lit.v,
    deliver: (text, _f, judged, whole) => { if (whole) wall.push({ text, judged }); },
    settled: (why) => settledWhy.push(why),
  });
  return { hold, wall, settledWhy };
}
{
  const lit = { v: false };
  const { hold, wall } = ringHarness(lit);
  hold.spoken("Mira, este es el widget de archivos.", true);
  await sleep(150);                                               // five fail-open deadlines go by
  assert.deepEqual(wall, [], "with the orb OFF a verdict-less turn was painted anyway — the wall said «heard»");
  assert.equal(hold.pending(), 1, "…and it must still be waiting for its verdict, not lost");
  hold.verdict("Mira, este es el widget de archivos.", false);
  assert.deepEqual(wall, [], "the late AMBIENT verdict drops it");
  assert.equal(hold.pending(), 0);
}
{
  const lit = { v: false };
  const { hold, wall } = ringHarness(lit);
  hold.spoken("Johnny, mira esto", true);
  await sleep(100);
  hold.verdict("Johnny, mira esto", true);
  assert.deepEqual(wall.map(w => w.text), ["Johnny, mira esto"], "a late DIRECTED verdict still paints it");
}
{
  const lit = { v: false };
  const { hold, wall, settledWhy } = ringHarness(lit, 90);
  hold.spoken("nadie dice nada", true);
  await sleep(250);
  assert.deepEqual(wall, [], "a turn never ruled with the orb off is not his words to zaelar");
  assert.equal(hold.pending(), 0, "…and it is dropped at the ceiling, not held forever");
  assert.ok(settledWhy.includes("dropped"), "the provisional caption must be told to go");
}
{
  const lit = { v: true };
  const { hold, wall } = ringHarness(lit);
  hold.spoken("Johnny, y otra cosa", true);
  await sleep(80);
  assert.deepEqual(wall.map(w => w.text), ["Johnny, y otra cosa"],
    "with the orb ON the fail-open still paints — never lose a word he said TO zaelar");
}
{
  const { readFileSync } = await import("node:fs");
  const src = readFileSync(new URL("../../../../frontend/app/services/sse.js", import.meta.url), "utf8");
  assert.ok(/listening:\s*\(\)\s*=>\s*paintsProvisional\(store\.attentionMode\(\),\s*store\.attentionHit\(\)\)/.test(src),
    "the hold must ask the ORB whether it may fail open");
  assert.ok(/holdSpokenTurn\(desktop, d\.text, isFinal\);[\s\S]{0,400}if \(paintsProvisional\(store\.attentionMode\(\), store\.attentionHit\(\)\)\) captionPartial\(""\);/.test(src),
    "the FINAL segment rewrote the caption with the ring off — the dashed line of his screenshot");
}

console.log("ok — the room is not the operator (14 groups)");
