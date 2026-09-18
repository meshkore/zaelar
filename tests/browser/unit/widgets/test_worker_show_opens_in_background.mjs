// ============================================================================
// test_worker_show_opens_in_background.mjs — fix04, session 6d19df41, node 4.149.
//
// THE OPERATOR'S REPORT (session 6d19df41): «Hey. Why are you open the documents
// right now? I set open my email». A ghost "Scarborough" errand commissioned its
// `documento` sheet (src `worker:1`), and the show came to the FRONT over the
// email flow he was in.
//
// THE MECHANISM: a worker-commissioned card still OPENS — placed in free space,
// data rendering as usual — but never TAKES FOCUS over what he is looking at.
// `sse.js` marks worker-src shows as `background:true`; both hosts honor it
// (desktop skips `_bringFront`, mobile Deck skips `_goTo`).
//
// This MOUNTS the real `sse.js` handler over the real `store.js` with a stub
// host and replays the three provenances: worker / flash / user-echo.
//
// Run: node tests/browser/unit/widgets/test_worker_show_opens_in_background.mjs
// ============================================================================
import assert from "node:assert/strict";

const mem = new Map([["hb_lang", "es"], ["hb_i18n_es", JSON.stringify({})]]);
globalThis.localStorage = { getItem: k => (mem.has(k) ? mem.get(k) : null),
                            setItem: (k, v) => mem.set(k, String(v)), removeItem: k => mem.delete(k) };
globalThis.fetch = async () => ({ ok: true, json: async () => ({}), text: async () => "" });
globalThis.document = { documentElement: { lang: "es", setAttribute(){}, style: { setProperty(){} } },
                        querySelectorAll: () => [], querySelector: () => null, addEventListener(){},
                        createElement: () => ({ style: {}, classList: { add(){}, remove(){} },
                                                appendChild(){}, setAttribute(){} }),
                        head: { appendChild(){} }, body: { appendChild(){} } };
globalThis.window = { addEventListener(){}, location: { href: "http://localhost/" } };
let sink = null;
globalThis.EventSource = class { constructor() { sink = this; } };

await import("../../../../frontend/app/core/store.js?v=2");
const { openSSE } = await import("../../../../frontend/app/services/sse.js?v=2");
const calls = [];
const desktop = { show(id, opts){ calls.push([id, opts]); }, close(){}, closeAll(){},
                  refreshData(){}, createWidget(){}, modifyWidget(){}, onDeleted(){},
                  showConfirm(){}, hideConfirm(){}, move(){}, resize(){}, fullscreen(){},
                  refreshRegistry(){} };
openSSE(desktop);
assert.ok(sink && typeof sink.onmessage === "function", "the SSE handler did not mount");
const push = (o) => sink.onmessage({ data: JSON.stringify(o) });

// ── 1. the ghost errand's show: opens, but in background ─────────────────────────────────────────────────
push({ kind: "widget", label: "show", id: "documento", src: "worker:1", data: { title: "Scarborough" } });
assert.equal(calls.length, 1, "a worker-commissioned show must still OPEN the card");
assert.equal(calls[0][0], "documento");
assert.equal(calls[0][1] && calls[0][1].background, true,
  "THE BUG: a worker show took focus over his email flow — it must open in background");
assert.equal(calls[0][1] && calls[0][1].data && calls[0][1].data.title, "Scarborough",
  "background must not drop the pushed data");

// ── 2. voice-ordered shows still come to the front ────────────────────────────────────────────────────────
for (const evt of [{ kind: "widget", label: "show", id: "mensajeria", src: "flash" },
                   { kind: "widget", label: "show", id: "mensajeria" }]) {
  calls.length = 0;
  push(evt);
  assert.equal(calls.length, 1, `a ${evt.src || "sourceless"} show must open the card`);
  assert.ok(!calls[0][1] || calls[0][1].background !== true,
    `a ${evt.src || "sourceless"} show is his own order — it must come to the front`);
}

// ── 3. the canvas echo stays silent (V2-261, unchanged) ───────────────────────────────────────────────────
calls.length = 0;
push({ kind: "widget", label: "show", id: "mensajeria", src: "user" });
assert.equal(calls.length, 0, "a canvas report is not an order — still ignored");

console.log("ok: worker shows open in background, his own shows front, echo silent");
