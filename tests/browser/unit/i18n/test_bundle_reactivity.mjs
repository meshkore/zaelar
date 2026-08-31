// REGRESSION 2026-08-09 — `t()` must reconcile when the BUNDLE gains keys, not only when the LANGUAGE changes.
//
// The actual bug: `t()` depended solely on `store.lang()`, and `setLang` is a no-op when the value does not change
// (Solid semantics, `Object.is`). On startup, the UI renders with the CACHED bundle in localStorage; when the
// backend response contained NEW keys, they were stored in memory but NOTHING re-rendered → the new strings
// remained as their raw key («debug.col_time») until the language was changed or localStorage was cleared.
// The operator saw it in the viewer: column labels and filter chips displaying the key instead of the text.
//
// This test wires up the REAL module with a stale localStorage and a fetch that returns a new key, and requires
// a reactive effect to see the raw key FIRST and the text AFTERWARD — that is, that a re-render occurred.
import assert from "node:assert/strict";

// Browser stubs BEFORE importing (the modules read localStorage at import time).
const mem = new Map([
  ["hb_lang", "es"],
  ["hb_i18n_es", JSON.stringify({ "col.old": "Antigua" })],   // STALE bundle: it does not have the new key
]);
globalThis.localStorage = {
  getItem: (k) => (mem.has(k) ? mem.get(k) : null),
  setItem: (k, v) => mem.set(k, String(v)),
  removeItem: (k) => mem.delete(k),
};
globalThis.fetch = async (url) => ({
  json: async () => (String(url).includes("/state")
    ? { active: "es" }
    : { code: "es", strings: { "col.old": "Antigua", "col.new": "Hora" } }),   // the backend ALREADY has the new one
});

// `?v=2` REQUIRED: this is the specifier with which i18n.js imports store/reactive. Without it, node (and the
// browser) resolve ANOTHER instance of the reactive module and the effect is registered in a different graph —
// the same duplicate-module issue that cost an entire session in V2-087.
const { t, initI18n, loadBundle } = await import("../../../../frontend/app/core/i18n.js?v=2");
const { createEffect } = await import("../../../../frontend/app/core/reactive.js?v=2");

const seen = [];
createEffect(() => seen.push(t("col.new")));      // this is how the UI renders a label

await initI18n();
await new Promise((r) => setTimeout(r, 20));      // lets the in-flight fetch for `en` settle

assert.equal(seen[0], "col.new", "the first render comes from the stale cache → raw key (expected)");
assert.equal(seen.at(-1), "Hora",
  "t() did NOT re-render when the new bundle arrived: the language did not change and the reactive dependency was insufficient");
assert.ok(seen.length >= 2, "there was no re-render at all");

// An IDENTICAL re-fetch must not invalidate the entire tree (the comparison is by content, not by call).
const before = seen.length;
await loadBundle("es");
assert.equal(seen.length, before, "an identical bundle re-rendered anyway");

console.log("ok");
