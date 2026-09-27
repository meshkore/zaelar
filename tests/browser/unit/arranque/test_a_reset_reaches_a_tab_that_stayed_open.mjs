// ============================================================================
// test_a_reset_reaches_a_tab_that_stayed_open.mjs — V2-773, node 4.221.
//
// `make reset` bumps the wipe epoch and restarts the engine. The epoch was read at boot only, so a tab that
// stayed open across the reset kept every old card, and — worse — re-reported them to the restarted server as
// open (measured 2026-09-27: four result sheets and a document on what should have been a blank desktop).
// The SSE stream re-opens exactly when the engine is back: that re-open runs the boot's own takeover again.
//
// Run: node tests/browser/unit/arranque/test_a_reset_reaches_a_tab_that_stayed_open.mjs
// ============================================================================
import assert from "node:assert/strict";

function fakeStorage(seed = {}) {
  const m = new Map(Object.entries(seed));
  return {
    get length() { return m.size; },
    key: (i) => [...m.keys()][i] ?? null,
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, String(v)),
    removeItem: (k) => m.delete(k),
    _keys: () => [...m.keys()],
  };
}

const { takeoverOnReset } = await import("../../../../frontend/app/core/first-run.js?v=1");
// sse.js pulls the store and half the UI in at import; the seam is what a re-open calls, not the EventSource.
const src = (await import("node:fs")).readFileSync(new URL("../../../../frontend/app/services/sse.js", import.meta.url), "utf8");
const seamSrc = src.slice(src.indexOf("export function sweepOnReopen"), src.indexOf("\n}\n", src.indexOf("export function sweepOnReopen")) + 3);
const sweepOnReopen = new Function(seamSrc.replace("export function sweepOnReopen", "return function sweepOnReopen") )();

// ── 1. the boot's open does NOT sweep (main.js already did); every reconnect does ────────────────────────
{
  let swept = 0;
  assert.equal(sweepOnReopen(1, () => { swept++; }), false, "the first open is the boot");
  assert.equal(swept, 0);
  assert.equal(sweepOnReopen(2, () => { swept++; }), true, "THE BUG: a reconnect never re-read the epoch");
  assert.equal(sweepOnReopen(3, () => { swept++; }), true);
  assert.equal(swept, 2);
}

// ── 2. a sweep that fails never reaches the stream ───────────────────────────────────────────────────────
{
  assert.doesNotThrow(() => sweepOnReopen(2, () => { throw new Error("storage gone"); }));
  assert.doesNotThrow(() => sweepOnReopen(2, () => Promise.reject(new Error("epoch fetch failed"))));
}

// ── 3. the operator's case, end to end through the takeover: the tab obeyed epoch A, the server now says B ─
{
  const local = fakeStorage({ hb_wipe: "A", hb_desktop: '[{"id":"results::9194df-1"}]', hb_desktop_epoch: "A", unrelated: "keep" });
  const session = fakeStorage();
  let reloaded = 0;
  const took = await takeoverOnReset({ fetchEpoch: async () => "B", local, session, reload: () => reloaded++ });
  assert.equal(took, true, "a moved epoch on reconnect must sweep the tab");
  assert.equal(reloaded, 1, "and reload it once — the boot path then leaves the desktop blank and clears the server");
  assert.deepEqual(local._keys().sort(), ["hb_wipe", "unrelated"], `only our namespace goes — ${local._keys()}`);
  assert.equal(local.getItem("hb_wipe"), "B");
}

// ── 4. a reconnect with the SAME epoch (an engine restart without a reset) touches nothing ───────────────
{
  const local = fakeStorage({ hb_wipe: "A", hb_desktop: '[{"id":"agenda"}]' });
  const session = fakeStorage();
  let reloaded = 0;
  assert.equal(await takeoverOnReset({ fetchEpoch: async () => "A", local, session, reload: () => reloaded++ }), false);
  assert.equal(reloaded, 0, "a plain restart must not blink the operator's tab");
  assert.equal(local.getItem("hb_desktop"), '[{"id":"agenda"}]');
}
console.log("ok — a reset reaches a tab that stayed open");
