// placement.js — where a new card lands (V2-773, operator's rule 2026-09-27).
//
// «Cuando se coloca un nuevo widget busca hueco en la zona de la pantalla que está como más vacía y se van
// intentando colocar de forma inteligente.» Until now `_place` took the FIRST hole in column order, at the size
// of a loading tile (400×340) the card then outgrew: a 920×640 agenda dropped into a 400×340 pocket and grew
// over its neighbours. Two things fix that, and only one lives here: the canvas now places a card at the
// footprint it will actually have (desktop.js), and this module picks the spot.
//
// ONE engine for every automatic placement — a fresh card, the ▦ repack button and the least-overlap fallback
// — so a grown canvas and a tidied one read alike. Pure: rects in, a point out; nothing here touches the DOM.
//
// A candidate is scored by the EMPTY RECTANGLE it anchors: the free run to its right and below (until the
// next obstacle in its band, or the desk edge). The card goes to the corner of the largest such rectangle,
// which is what a person means by «the emptiest zone» — and because the anchor is a corner, the card sits
// tidily against the region's edge instead of floating in the middle of the void. Ties (an empty desk) break
// top-to-bottom, then left-to-right: the column stacking of V2-551.

/** Two rects overlap, counting a gap narrower than `pad` as touching. */
export function overlaps(a, b, pad = 12) {
  return !(a.right + pad <= b.left || a.left >= b.right + pad || a.bottom + pad <= b.top || a.top >= b.bottom + pad);
}

function coveredArea(r, obstacles) {
  let cover = 0;
  for (const o of obstacles) {
    const ow = Math.min(r.right, o.right) - Math.max(r.left, o.left);
    const oh = Math.min(r.bottom, o.bottom) - Math.max(r.top, o.top);
    if (ow > 0 && oh > 0) cover += ow * oh;
  }
  return cover;
}

/** The empty rectangle anchored at (x, y) for a w×h card: free run right and down, in its own bands. */
export function anchoredRoom({ x, y, w, h, box, obstacles, pad = 12 }) {
  let right = box.x1, bottom = box.y1;
  for (const o of obstacles) {
    const inBand = o.bottom + pad > y && o.top - pad < y + h;
    if (inBand && o.left >= x + w && o.left - pad < right) right = o.left - pad;
    const inCol = o.right + pad > x && o.left - pad < x + w;
    if (inCol && o.top >= y + h && o.top - pad < bottom) bottom = o.top - pad;
  }
  return Math.max(0, right - x) * Math.max(0, bottom - y);
}

const snapUp = (n, g) => Math.ceil(n / g) * g;

/**
 * The spot for a w×h card. `box` = {x0, y0, x1, y1} (the usable canvas), `obstacles` = rects to avoid.
 * mode "free"  — the corner of the largest empty region (a fresh card).
 * mode "tight" — the first hole in column order (the ▦ repack: close the gaps, keep the sizes).
 * When nothing fits at all, the least-overlapping wholly-visible position, so the card is never half off the
 * desk and never piled in one corner. Returns {x, y, fits}.
 */
export function bestSpot({ w, h, box, obstacles = [], grid = 5, pad = 12, mode = "free" }) {
  const g = Math.max(1, grid | 0);
  const xmin = snapUp(box.x0, g), ymin = snapUp(box.y0, g);
  const step = mode === "tight" ? g : Math.max(g, 10);
  let best = null;
  for (let x = xmin; x + w <= box.x1; x += step) {
    for (let y = ymin; y + h <= box.y1; y += step) {
      const r = { left: x, top: y, right: x + w, bottom: y + h };
      if (obstacles.some(o => overlaps(r, o, pad))) continue;
      if (mode === "tight") return { x, y, fits: true };
      const room = anchoredRoom({ x, y, w, h, box, obstacles, pad });
      if (!best || room > best.room) best = { x, y, room };
    }
  }
  if (best) return { x: best.x, y: best.y, fits: true };
  return { ...leastOverlap({ w, h, box, obstacles, grid: g }), fits: false };
}

/** The wholly-visible position whose overlap with existing cards is smallest (nothing fits at all). */
export function leastOverlap({ w, h, box, obstacles = [], grid = 5 }) {
  const g = Math.max(1, grid | 0), step = Math.max(g, 20);
  const xmin = snapUp(box.x0, g), ymin = snapUp(box.y0, g);
  const maxX = Math.max(xmin, box.x1 - w), maxY = Math.max(ymin, box.y1 - h);
  let best = { x: xmin, y: ymin, cover: Infinity };
  for (let x = xmin; x <= maxX; x += step) {
    for (let y = ymin; y <= maxY; y += step) {
      const cover = coveredArea({ left: x, top: y, right: x + w, bottom: y + h }, obstacles);
      if (cover < best.cover) { best = { x, y, cover }; if (!cover) return { x, y }; }
    }
  }
  return { x: best.x, y: best.y };
}
