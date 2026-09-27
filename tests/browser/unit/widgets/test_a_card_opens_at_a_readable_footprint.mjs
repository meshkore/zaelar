// test_a_card_opens_at_a_readable_footprint.mjs — V2-773, operator's rule 2026-09-27: «los widgets tienen que
// abrirse a tamaños correctos… el de mensajes se abre alargado, muy alargado». Measured: 1700×380 on a 16" desk.
// Run: node tests/browser/unit/widgets/test_a_card_opens_at_a_readable_footprint.mjs
import assert from "node:assert/strict";
const { saneFootprint } = await import("../../../../frontend/app/widgets/footprint.js?v=1");
const desk = { canvasW: 2500, canvasH: 1250 };   // his 16" desk, minus the chrome

// 1. the strip he saw becomes a readable card
{
  const s = saneFootprint({ w: 1700, h: 380, ...desk });
  assert.ok(s.w <= 1250, `never wider than half the desk — ${s.w}`);
  assert.ok(s.w / s.h <= 1.7, `THE BUG: a strip — ${s.w}×${s.h}`);
  assert.ok(s.h >= 600, `tall enough to read messages in — ${s.h}`);
  assert.equal(s.changed, true);
}
// 2. a small piece keeps its measured size: the clock is not a strip
{
  const s = saneFootprint({ w: 260, h: 160, ...desk });
  assert.deepEqual([s.w, s.h, s.changed], [260, 160, false]);
}
// 3. a sliver gets width
{
  const s = saneFootprint({ w: 200, h: 900, ...desk });
  assert.ok(s.w / s.h >= 0.45 && s.w >= 240, `${s.w}×${s.h}`);
}
// 4. a sane card is untouched, and nothing ever exceeds the desk
{
  assert.equal(saneFootprint({ w: 720, h: 560, ...desk }).changed, false);
  const s = saneFootprint({ w: 5000, h: 4000, canvasW: 1200, canvasH: 700 });
  assert.ok(s.w <= 1200 && s.h <= 700);
}
console.log("ok — a card opens at a readable footprint");
