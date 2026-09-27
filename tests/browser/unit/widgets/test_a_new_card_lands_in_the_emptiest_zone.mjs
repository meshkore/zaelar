// test_a_new_card_lands_in_the_emptiest_zone.mjs — V2-773, operator's rule 2026-09-27: «busca hueco en la zona de
// la pantalla que está como más vacía». Run: node tests/browser/unit/widgets/test_a_new_card_lands_in_the_emptiest_zone.mjs
import assert from "node:assert/strict";
const { bestSpot, overlaps, anchoredRoom } = await import("../../../../frontend/app/widgets/placement.js?v=1");
const box = { x0: 14, y0: 70, x1: 2486, y1: 1180 };   // his 16" desk, minus the chrome
const rect = (x, y, w, h) => ({ left: x, top: y, right: x + w, bottom: y + h });
const clear = (r, obs) => !obs.some(o => overlaps(r, o));

// 1. an empty desk: the top-left corner, on the grid
{
  const s = bestSpot({ w: 920, h: 640, box, obstacles: [] });
  assert.deepEqual([s.x, s.y, s.fits], [15, 70, true]);
}
// 2. one card at the top-left: the next lands beside it, not over it, and wholly on the desk
{
  const obs = [rect(15, 70, 920, 640)];
  const s = bestSpot({ w: 720, h: 560, box, obstacles: obs });
  assert.ok(s.fits && clear(rect(s.x, s.y, 720, 560), obs), `overlaps: ${s.x},${s.y}`);
  assert.ok(s.x + 720 <= box.x1 && s.y + 560 <= box.y1);
}
// 3. THE RULE: a pocket that fits exactly at the top-left versus a wide-open right half — the open half wins.
//    First-fit column order took the pocket (x=15, wedged between two cards); the emptiest zone is to the right.
{
  const obs = [rect(15, 70, 600, 300), rect(15, 70 + 300 + 20 + 340 + 20, 600, 400), rect(630, 70, 300, 1100)];
  const s = bestSpot({ w: 500, h: 340, box, obstacles: obs });
  assert.ok(s.fits && clear(rect(s.x, s.y, 500, 340), obs));
  assert.ok(s.x > 930, `THE BUG: wedged into the pocket at x=${s.x} instead of the open right half`);
  assert.equal(s.y, 70, "…and against the region's top edge, not floating");
}
// 4. the ▦ repack keeps column order: the first hole, tight against its neighbour
{
  const obs = [rect(15, 70, 600, 300)];
  const s = bestSpot({ w: 500, h: 340, box, obstacles: obs, mode: "tight" });
  assert.deepEqual([s.x, s.y], [15, 70 + 300 + 15]);   // 12px gap, snapped up to the 5px grid
}
// 5. nothing fits: least overlap, and never half off the desk
{
  const obs = [rect(15, 70, 1200, 1100), rect(1230, 70, 1250, 1100)];
  const s = bestSpot({ w: 900, h: 700, box, obstacles: obs });
  assert.equal(s.fits, false);
  assert.ok(s.x >= box.x0 && s.y >= box.y0 && s.x + 900 <= box.x1 && s.y + 700 <= box.y1, `${s.x},${s.y}`);
}
// 6. the room a corner anchors stops at the next card in its band
{
  const room = anchoredRoom({ x: 15, y: 70, w: 400, h: 300, box, obstacles: [rect(1000, 0, 200, 2000)], pad: 12 });
  assert.equal(room, (1000 - 12 - 15) * (box.y1 - 70));
}
console.log("ok — a new card lands in the emptiest zone");
