// ============================================================================
// test_the_canvas_does_not_obey_its_own_echo.mjs — V2-261, nodo 4.37.
//
// THE BUG, measured by the harness and seen on screen by the operator: two seconds after the good card opened,
// ANOTHER browser card, BASE and empty (“opening tab…”), appeared on top. Nobody opened it: it was an ECHO
// from the canvas itself.
//
//   1. the task emits  widget/show id=navegador::t2      → the frontend opens the instance
//   2. desktop._persist() → POST /api/canvas/state        → the canvas reports what it has open
//   3. voice_api.canvas_state NORMALIZES navegador::t2 → «navegador», compares it with the previous set, and emits
//      widget/show id=navegador src=user  (V2-039 audit: leave on the timeline what the operator
//      opens/closes manually, which used to be a SILENT action)
//   4. …and that audit travels through the SAME channel as the COMMANDS, so it came back here and was executed
//
// Studio evidence: `['navegador::t1'] → ['navegador::t1','navegador']`, and `['results','navegador::t2'] →
// […,'navegador']`. Always 2 seconds later. It had been SEEN since V2-047 F9 —the comment in `voice_api.py` cites
// “two browsers, one blank”— and had only been INSTRUMENTED.
//
// The missing rule: **a report of what already happened is not an order**, and the one who sent it is precisely the
// one who has nothing to do with it. It is cut off in `sse.js` because that is the ONLY place through which both hosts
// (desktop and mobile) receive this — not in the route, where the audit must continue emitting with its
// label so observability and the Master continue counting it the same way.
//
// It MOUNTS the real handler and feeds it the events: a source test would say that the condition exists, not that it
// filters. Run: node tests/browser/unit/frontera/test_the_canvas_does_not_obey_its_own_echo.mjs
// ============================================================================
import assert from "node:assert/strict";

const mem = new Map([["hb_lang", "es"], ["hb_i18n_es", JSON.stringify({})]]);
globalThis.localStorage = {
  getItem: k => (mem.has(k) ? mem.get(k) : null),
  setItem: (k, v) => mem.set(k, String(v)),
  removeItem: k => mem.delete(k),
};
globalThis.fetch = async () => ({ ok: true, json: async () => ({}), text: async () => "" });
globalThis.document = { documentElement: { lang: "es", setAttribute(){}, style: { setProperty(){} } },
                        querySelectorAll: () => [], querySelector: () => null,
                        addEventListener(){}, createElement: () => ({ style:{}, classList:{ add(){}, remove(){} },
                                                                      appendChild(){}, setAttribute(){} }),
                        head: { appendChild(){} }, body: { appendChild(){} } };
globalThis.window = { addEventListener(){}, location: { href: "http://localhost/" } };

let sink = null;
globalThis.EventSource = class { constructor(){ sink = this; } };

const { openSSE } = await import("../../../../frontend/app/services/sse.js?v=2");

const llamadas = [];
const desktop = {
  show: (id) => llamadas.push(["show", id]),
  close: (id) => llamadas.push(["close", id]),
  closeAll: () => llamadas.push(["closeAll", null]),
  refreshData: (id) => llamadas.push(["data", id]),
  createWidget(){}, modifyWidget(){}, onDeleted(){}, showConfirm(){}, hideConfirm(){}, move(){}, resize(){},
  fullscreen(){}, refreshRegistry(){},
};
openSSE(desktop);
assert.ok(sink && typeof sink.onmessage === "function", "no se pudo montar el manejador de SSE");
const push = (obj) => sink.onmessage({ data: JSON.stringify(obj) });

// 1) an ORDER from the brain is obeyed — this is what opens the good card
push({ kind: "widget", label: "show", id: "navegador::t2" });
assert.deepEqual(llamadas, [["show", "navegador::t2"]]);

// 2) the canvas's own ECHO is NOT. This is the exact event that painted the phantom card.
llamadas.length = 0;
push({ kind: "widget", label: "show", id: "navegador", src: "user" });
assert.deepEqual(llamadas, [], "el canvas obedeció su propio informe: tarjeta BASE vacía encima de la real");

// 3) …nor the close echo: if the operator closes a card manually, the canvas has ALREADY closed it. Closing it again
//    is not idempotent when what arrives is the BASE of an instance — it would close something else.
llamadas.length = 0;
push({ kind: "widget", label: "close", id: "navegador", src: "user" });
assert.deepEqual(llamadas, [], "el eco de cierre volvía a entrar como orden");

// 4) the other direction, which is what prevents “fixing it” by shutting down the entire channel: a REAL close order
//    still closes, and “close everything” (without an id) does too.
llamadas.length = 0;
push({ kind: "widget", label: "close", id: "agenda" });
push({ kind: "widget", label: "close" });
assert.deepEqual(llamadas, [["close", "agenda"], ["closeAll", null]]);

// 5) `data` is NOT a canvas order but a repaint notification, and it must continue passing through: if it were filtered
//    by origin, an open sheet would stop refreshing and the failure would be silent.
llamadas.length = 0;
push({ kind: "widget", label: "data", id: "results::t1" });
push({ kind: "widget", label: "data", id: "results::t1", src: "user" });
assert.deepEqual(llamadas, [["data", "results::t1"], ["data", "results::t1"]]);

// 6) and the reason this affects MY sheet as well as the browser: as soon as the sheet is instantiated (V2-259), its
//    normalization produces exactly the same echo.
llamadas.length = 0;
push({ kind: "widget", label: "show", id: "results::t7" });
push({ kind: "widget", label: "show", id: "results", src: "user" });
assert.deepEqual(llamadas, [["show", "results::t7"]],
  "la hoja instanciada hereda el fantasma del navegador si el eco no se corta");

console.log("ok");
