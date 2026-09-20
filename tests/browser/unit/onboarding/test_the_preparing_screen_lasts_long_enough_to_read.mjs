// ============================================================================
// test_the_preparing_screen_lasts_long_enough_to_read.mjs — V2-731, node 4.163.
//
// THE OPERATOR'S REPORT (2026-09-20, right after choosing a language): «ha
// salido como una pequeña pantalla que ha durado un segundo o dos y no sé qué
// era. Si hay un loader o una pantalla tiene que tener un progress bar o algo,
// pero como mínimo debe durar dos segundos para que la gente lo vea».
//
// AND HIS CORRECTION, the same evening, once it had a floor and a bar: «si no
// hay que hacer nada para idiomas inicializados, mejor no mostrar NADA en ese
// caso». Which is the better rule, and it is the one measured first here: for a
// language that is already initialized the engine counts ZERO steps, and then
// there is no screen, no floor and nothing to read — the picker he is looking
// at simply fades. The floor is for a wait that is real.
//
// This MOUNTS the real sse.js handler over the real store.js, because both
// halves are only worth anything if the transport actually decides them: a test
// that called `beginLangOnboardLoading()` itself would pass with the wiring cut.
//
// Run: node tests/browser/unit/onboarding/test_the_preparing_screen_lasts_long_enough_to_read.mjs
// ============================================================================
import assert from "node:assert/strict";

const mem = new Map([["hb_lang", "en"], ["hb_i18n_en", JSON.stringify({})]]);
globalThis.localStorage = { getItem: k => (mem.has(k) ? mem.get(k) : null),
                            setItem: (k, v) => mem.set(k, String(v)), removeItem: k => mem.delete(k) };
const fetched = [];
globalThis.fetch = async (u) => { fetched.push(String(u));
                                  return { ok: true, json: async () => ({}), text: async () => "" }; };
globalThis.document = { documentElement: { lang: "en", setAttribute(){}, style: { setProperty(){} } },
                        querySelectorAll: () => [], querySelector: () => null, addEventListener(){},
                        createElement: () => ({ style: {}, classList: { add(){}, remove(){} },
                                                appendChild(){}, setAttribute(){} }),
                        head: { appendChild(){} }, body: { appendChild(){} } };
globalThis.window = { addEventListener(){}, location: { href: "http://localhost/" } };
let sink = null;
globalThis.EventSource = class { constructor() { sink = this; } };

const store = await import("../../../../frontend/app/core/store.js?v=2");
const { openSSE } = await import("../../../../frontend/app/services/sse.js?v=2");
const desktop = { show(){}, close(){}, closeAll(){}, refreshData(){}, createWidget(){}, modifyWidget(){},
                  onDeleted(){}, showConfirm(){}, hideConfirm(){}, move(){}, resize(){}, fullscreen(){},
                  refreshRegistry(){} };
openSSE(desktop);
assert.ok(sink && typeof sink.onmessage === "function", "the SSE handler did not mount");
const push = (o) => sink.onmessage({ data: JSON.stringify(o) });
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

assert.ok(store.LANG_LOADER_FLOOR_MS >= 2000,
  `«como mínimo debe durar dos segundos»: the floor is ${store.LANG_LOADER_FLOOR_MS} ms`);

// ── 1. an ALREADY-INITIALIZED language: nothing to do, so nothing is shown ───────────────────────────────
store.setLangOnboardOpen(true);
push({ kind: "language", label: "detected", phase: "detected", code: "en", total: 0,
       loading: "Preparing English…", strings: {} });

assert.equal(store.langOnboardPreparing(), false,
  "THE BUG: a language with nothing to prepare still drew a preparing screen");
assert.equal(store.langOnboardHold(), false,
  "and held the veil open for two seconds to show it — «mejor no mostrar NADA en ese caso»");
assert.equal(store.langOnboardProgress(), null, "there is no progress to report on no work");

push({ kind: "language", label: "ready", phase: "ready", code: "en" });
await sleep(700);
assert.equal(store.langOnboardOpen(), false,
  "with nothing to watch, the veil goes as soon as the language is ready");

// ── 2. a language it has to BUILD: the screen appears, and it is readable ────────────────────────────────
store.setLangOnboardOpen(true);
const t0 = Date.now();
push({ kind: "language", label: "detected", phase: "detected", code: "ja", total: 3,
       loading: "準備しています…", strings: {} });

assert.equal(store.langOnboardPreparing(), true, "a real wait earns a screen");
assert.equal(store.langOnboardLoading(), "準備しています…", "the screen has to SAY what it is doing");
assert.ok(store.langOnboardHold(), "THE BUG: nothing held the veil, so a fast finish closed it instantly");
assert.deepEqual(store.langOnboardProgress(), { done: 0, total: 3 },
  "the bar needs its denominator from the first event, not once the steps start arriving");

const before = fetched.length;
push({ kind: "language", label: "progress", phase: "progress", done: 1, total: 3 });
assert.deepEqual(store.langOnboardProgress(), { done: 1, total: 3 }, "a step must move the bar");
assert.equal(fetched.length, before,
  "a progress report is not a language change: it must not refetch the bundle");

// even if the rest finishes at once, the screen stays long enough to be read
push({ kind: "language", label: "progress", phase: "progress", done: 3, total: 3 });
push({ kind: "language", label: "ready", phase: "ready", code: "ja" });
await sleep(900);
assert.ok(store.langOnboardOpen(),
  `THE BUG: the screen was gone after ${Date.now() - t0} ms — «no sé qué era»`);
assert.ok(store.langOnboardHold(), "and it is the floor holding it, not an accident of timing");

await sleep(store.LANG_LOADER_FLOOR_MS - (Date.now() - t0) + 900);
assert.equal(store.langOnboardHold(), false, "the floor must release itself");
assert.equal(store.langOnboardOpen(), false,
  `the veil must close once it has been readable: ${Date.now() - t0} ms after the screen appeared`);
assert.ok(Date.now() - t0 >= store.LANG_LOADER_FLOOR_MS, "and never before the floor");

// ── 3. a reconnect must not restart the clock he is already watching ─────────────────────────────────────
push({ kind: "language", label: "detected", phase: "detected", code: "ja", total: 3,
       loading: "準備しています…", strings: {} });
assert.equal(store.langOnboardHold(), false, "a second «detected» must not re-arm a floor already served");

console.log("ok: nothing is shown for nothing, and a real wait is readable");
