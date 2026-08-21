// ============================================================================
// test_the_canvas_does_not_obey_its_own_echo.mjs — V2-261, nodo 4.37.
//
// EL BUG, medido por el arnés y visto en pantalla por el operador: dos segundos después de abrirse la tarjeta
// buena aparecía OTRA tarjeta de navegador, BASE y vacía («abriendo pestaña…»), encima. No la abría nadie: era
// un ECO del propio canvas.
//
//   1. la tarea emite  widget/show id=navegador::t2      → el frontend abre la instancia
//   2. desktop._persist() → POST /api/canvas/state        → el canvas informa de lo que tiene abierto
//   3. voice_api.canvas_state NORMALIZA navegador::t2 → «navegador», compara con el conjunto anterior y emite
//      widget/show id=navegador src=user  (auditoría V2-039: dejar en la línea de tiempo lo que el operador
//      abre/cierra a mano, que antes era una acción SILENCIOSA)
//   4. …y esa auditoría viaja por el MISMO canal que las ÓRDENES, así que volvía aquí y se ejecutaba
//
// Evidencia del plató: `['navegador::t1'] → ['navegador::t1','navegador']`, y `['results','navegador::t2'] →
// […,'navegador']`. Siempre 2 s después. Estaba VISTO desde V2-047 F9 —el comentario de `voice_api.py` cita
// «two browsers, one blank»— y solo se había INSTRUMENTADO.
//
// La regla que faltaba: **un informe de lo que ya pasó no es una orden**, y el que lo mandó es justamente quien
// no tiene nada que hacer con él. Se corta en `sse.js` porque es el ÚNICO sitio por el que los dos hosts
// (escritorio y móvil) reciben esto — no en la ruta, donde la auditoría tiene que seguir emitiendo con su
// etiqueta para que la observabilidad y el Master la sigan contando igual.
//
// MONTA el manejador de verdad y le mete los eventos: un test de fuente diría que la condición existe, no que
// filtra. Run: node tests/browser/unit/frontera/test_the_canvas_does_not_obey_its_own_echo.mjs
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

// 1) una ORDEN del cerebro se obedece — es lo que abre la tarjeta buena
push({ kind: "widget", label: "show", id: "navegador::t2" });
assert.deepEqual(llamadas, [["show", "navegador::t2"]]);

// 2) el ECO del propio canvas NO. Este es el evento exacto que pintaba la tarjeta fantasma.
llamadas.length = 0;
push({ kind: "widget", label: "show", id: "navegador", src: "user" });
assert.deepEqual(llamadas, [], "el canvas obedeció su propio informe: tarjeta BASE vacía encima de la real");

// 3) …y tampoco el de cierre: si el operador cierra una tarjeta a mano, el canvas YA la cerró. Volver a
//    cerrarla no es idempotente cuando lo que llega es la BASE de una instancia — cerraría otra cosa.
llamadas.length = 0;
push({ kind: "widget", label: "close", id: "navegador", src: "user" });
assert.deepEqual(llamadas, [], "el eco de cierre volvía a entrar como orden");

// 4) la otra dirección, que es la que impide «arreglarlo» apagando el canal entero: una orden REAL de cerrar
//    sigue cerrando, y «ciérralo todo» (sin id) también.
llamadas.length = 0;
push({ kind: "widget", label: "close", id: "agenda" });
push({ kind: "widget", label: "close" });
assert.deepEqual(llamadas, [["close", "agenda"], ["closeAll", null]]);

// 5) `data` NO es una orden de canvas sino un aviso de repintado, y tiene que seguir pasando: si se filtrara
//    por procedencia, una hoja abierta dejaría de refrescarse y el fallo sería mudo.
llamadas.length = 0;
push({ kind: "widget", label: "data", id: "results::t1" });
push({ kind: "widget", label: "data", id: "results::t1", src: "user" });
assert.deepEqual(llamadas, [["data", "results::t1"], ["data", "results::t1"]]);

// 6) y la razón por la que esto es MÍO además de del navegador: en cuanto la hoja se instancia (V2-259), su
//    normalización produce exactamente el mismo eco.
llamadas.length = 0;
push({ kind: "widget", label: "show", id: "results::t7" });
push({ kind: "widget", label: "show", id: "results", src: "user" });
assert.deepEqual(llamadas, [["show", "results::t7"]],
  "la hoja instanciada hereda el fantasma del navegador si el eco no se corta");

console.log("ok");
