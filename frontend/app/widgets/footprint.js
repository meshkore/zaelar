// footprint.js — the footprint a card that declares no size opens with (V2-773, operator's rule 2026-09-27).
//
// «Los widgets tienen que abrirse a tamaños correctos… el de mensajes se abre en unos formatos que no son
// interesantes: alargado, muy alargado.» Measured on his 16" desk: the messaging card, which declares no
// `manifest.size`, froze at its first rendered footprint — 1700×380, a strip nobody can read a message in —
// because a card with no declared size takes whatever its content measured on first paint (V2-630 freezes
// the FIRST render so the content never resizes the card again; it never judged that first render).
//
// A footprint is judged against the desk it opens on, never in absolute pixels: a small piece (a clock at
// 260×160) keeps its measured size, a content piece that measured as a strip or a sliver is brought back to a
// readable proportion — never wider than half the desk, and with a height that reads as a card, not a bar.
// The operator resizes from there; his gesture is persisted and never touched here (`haveW`/`haveH`).

export const MAX_SHARE_W = 0.5;      // a card that declared nothing is never wider than half the desk
export const TALL_SHARE_H = 0.62;    // …and when it has to grow, it grows to a readable card, not the whole desk
export const RATIO_MAX = 1.7;        // wider than this reads as a strip
export const RATIO_MIN = 0.45;       // narrower than this reads as a sliver

/** {w, h} for a first render measured at (w, h) on a desk of (canvasW, canvasH). Pure. */
export function saneFootprint({ w, h, canvasW, canvasH, minW = 240, minH = 150 }) {
  let W = Math.max(minW, Number(w) || 0), H = Math.max(minH, Number(h) || 0);
  const cw = Math.max(minW, Number(canvasW) || 0), ch = Math.max(minH, Number(canvasH) || 0);
  const maxW = Math.max(minW, Math.round(cw * MAX_SHARE_W));
  if (W > maxW) W = maxW;
  if (W / H > RATIO_MAX) H = Math.max(H, Math.min(Math.round(ch * TALL_SHARE_H), Math.round(W / 1.3)));
  if (W / H < RATIO_MIN) W = Math.min(maxW, Math.max(W, Math.round(H * 0.6)));
  return { w: Math.min(W, cw), h: Math.min(H, ch), changed: W !== (Number(w) || 0) || H !== (Number(h) || 0) };
}
