// feedback-images.js — turning a screenshot into something a bug report can carry (V2-695).
//
// The operator asked for it in the plainest terms: «can we allow to paste or upload an image to be
// added to the request?». Half of any real bug report is «look at what my screen says», and until
// today there was nowhere to put it.
//
// WHY THE PICTURE IS SHRUNK HERE, in the browser, before anything is sent. The feedback POST is a
// live 5-second call with NO queue and NO local copy: if it fails, the only thing that survives is
// the text still sitting in the box. A 6 MB phone screenshot turns a report that would have arrived
// into one that times out. So the image is re-encoded to something a report can afford, and the
// budget is a CONSTANT other code reads rather than a number repeated in four places.
//
// Everything above `prepare()` is pure arithmetic on purpose: it runs under Node in a test, which is
// how the budget gets a ratchet without a browser.

/** The whole budget, in one object. The server enforces the same numbers — a client is not a guard. */
export const LIMITS = {
  maxShots: 3,             // three pictures say everything a report needs; the fourth is a folder
  maxSide: 1280,           // enough to read an error message, far from a retina screenshot
  maxBytes: 180_000,       // per image, AFTER re-encoding
  maxTotalBytes: 600_000,  // the whole report's worth of pictures
};

/** Is this something we can show? Only images — the operator's own answer when asked. */
export function isImage(file) {
  return !!file && typeof file.type === "string" && /^image\//i.test(file.type);
}

/** Bytes already spent by the shots held in the form. */
export function spent(shots) {
  return (shots || []).reduce((n, s) => n + (Number(s && s.bytes) || 0), 0);
}

/** What is left of the budget, in bytes — never negative. */
export function budgetLeft(shots) {
  return Math.max(0, LIMITS.maxTotalBytes - spent(shots));
}

/**
 * May one more shot of `bytes` join these? Returns "" when it may, or the REASON key when it may not,
 * so the caller can say WHICH limit was hit instead of failing silently. A refusal the operator cannot
 * read is the same as losing the picture.
 */
export function refusal(shots, bytes) {
  if ((shots || []).length >= LIMITS.maxShots) return "feedback.tooManyShots";
  if ((Number(bytes) || 0) > budgetLeft(shots)) return "feedback.shotsTooBig";
  return "";
}

/** The box this image fits into, keeping its shape. Never ENLARGES a small picture. */
export function targetSize(w, h, maxSide = LIMITS.maxSide) {
  const W = Math.max(1, Math.round(Number(w) || 1));
  const H = Math.max(1, Math.round(Number(h) || 1));
  const longest = Math.max(W, H);
  if (longest <= maxSide) return { w: W, h: H };
  const k = maxSide / longest;
  return { w: Math.max(1, Math.round(W * k)), h: Math.max(1, Math.round(H * k)) };
}

// The ladder `prepare` walks down until the picture fits: first give up quality, then give up size.
// Quality is cheaper than pixels for a screenshot of text, which is what these almost always are.
const _QUALITIES = [0.82, 0.68, 0.55, 0.42];
const _SHRINKS = [1, 0.75, 0.56, 0.42];

async function _encode(bitmap, side, quality, mime) {
  const { w, h } = targetSize(bitmap.width, bitmap.height, side);
  const canvas = document.createElement("canvas");
  canvas.width = w; canvas.height = h;
  canvas.getContext("2d").drawImage(bitmap, 0, 0, w, h);
  const blob = await new Promise(res => canvas.toBlob(res, mime, quality));
  return blob;
}

function _toBase64(blob) {
  return new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(String(fr.result || "").split(",")[1] || "");
    fr.onerror = () => rej(fr.error || new Error("read_failed"));
    fr.readAsDataURL(blob);
  });
}

/**
 * One file → one shot `{name, mime, bytes, data}` (base64, no data: prefix), or `null` when it cannot
 * be read at all. Never throws: a picture that will not decode must not take the report down with it.
 *
 * WebP where the browser has it (roughly half the bytes of JPEG at the same readability), JPEG
 * otherwise — `toBlob` hands back a PNG when it does not know the type, which is the worst of the
 * three for a screenshot, so the result's own `blob.type` decides, never our hope.
 */
export async function prepare(file, limits = LIMITS) {
  if (!isImage(file)) return null;
  let bitmap = null;
  try {
    bitmap = await createImageBitmap(file);
  } catch (_) {
    return null;
  }
  try {
    let best = null;
    for (const shrink of _SHRINKS) {
      for (const q of _QUALITIES) {
        let blob = await _encode(bitmap, Math.round(limits.maxSide * shrink), q, "image/webp");
        if (blob && blob.type !== "image/webp") blob = await _encode(bitmap, Math.round(limits.maxSide * shrink), q, "image/jpeg");
        if (!blob) continue;
        if (!best || blob.size < best.size) best = blob;
        if (blob.size <= limits.maxBytes) {
          return { name: String(file.name || "captura"), mime: blob.type || "image/jpeg",
                   bytes: blob.size, data: await _toBase64(blob) };
        }
      }
    }
    // Nothing fit. The smallest attempt still travels IF the caller's remaining budget takes it —
    // that judgement is `refusal`'s, not ours: a picture we shrank as far as we can is still the
    // best answer to «look at my screen», and silently dropping it would be the worse failure.
    if (!best) return null;
    return { name: String(file.name || "captura"), mime: best.type || "image/jpeg",
             bytes: best.size, data: await _toBase64(best) };
  } catch (_) {
    return null;
  } finally {
    try { bitmap.close(); } catch (_) {}
  }
}

/** The `src` a thumbnail points at. Kept here so the shot's shape is known in exactly one place. */
export function dataUrl(shot) {
  if (!shot || !shot.data) return "";
  return "data:" + (shot.mime || "image/jpeg") + ";base64," + shot.data;
}
