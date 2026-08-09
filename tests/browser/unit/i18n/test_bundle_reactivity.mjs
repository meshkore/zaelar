// REGRESIÓN 2026-08-09 — `t()` debe reconciliar cuando el BUNDLE gana claves, no solo cuando cambia el IDIOMA.
//
// El fallo real: `t()` dependía únicamente de `store.lang()`, y `setLang` es no-op si el valor no cambia
// (semántica Solid, `Object.is`). Al arrancar, la UI se pinta con el bundle CACHEADO en localStorage; cuando la
// respuesta del backend traía claves NUEVAS, se guardaban en memoria pero NADA se re-renderizaba → los strings
// nuevos se quedaban como su clave cruda («debug.col_time») hasta cambiar de idioma o vaciar el localStorage.
// El operador lo vio en el visor: rótulos de columna y chips de filtro mostrando la clave en vez del texto.
//
// Este test enchufa el módulo REAL con un localStorage rancio y un fetch que devuelve una clave nueva, y exige
// que un efecto reactivo vea PRIMERO la clave cruda y DESPUÉS el texto — es decir, que hubo re-render.
import assert from "node:assert/strict";

// Stubs de navegador ANTES de importar (los módulos leen localStorage en tiempo de import).
const mem = new Map([
  ["hb_lang", "es"],
  ["hb_i18n_es", JSON.stringify({ "col.old": "Antigua" })],   // bundle RANCIO: no tiene la clave nueva
]);
globalThis.localStorage = {
  getItem: (k) => (mem.has(k) ? mem.get(k) : null),
  setItem: (k, v) => mem.set(k, String(v)),
  removeItem: (k) => mem.delete(k),
};
globalThis.fetch = async (url) => ({
  json: async () => (String(url).includes("/state")
    ? { active: "es" }
    : { code: "es", strings: { "col.old": "Antigua", "col.new": "Hora" } }),   // el backend YA tiene la nueva
});

// `?v=2` OBLIGATORIO: es el especificador con el que i18n.js importa store/reactive. Sin él, node (y el
// navegador) resuelven OTRA instancia del módulo reactivo y el efecto se registra en un grafo distinto —
// el mismo módulo-duplicado que costó una sesión entera en V2-087.
const { t, initI18n, loadBundle } = await import("../../../../frontend/app/core/i18n.js?v=2");
const { createEffect } = await import("../../../../frontend/app/core/reactive.js?v=2");

const seen = [];
createEffect(() => seen.push(t("col.new")));      // así es como la UI pinta un rótulo

await initI18n();
await new Promise((r) => setTimeout(r, 20));      // deja asentar el fetch en vuelo de `en`

assert.equal(seen[0], "col.new", "el primer pintado sale de la caché rancia → clave cruda (esperado)");
assert.equal(seen.at(-1), "Hora",
  "t() NO se re-renderizó al llegar el bundle nuevo: el idioma no cambió y la dependencia reactiva se quedó corta");
assert.ok(seen.length >= 2, "no hubo re-render alguno");

// Un re-fetch IDÉNTICO no debe invalidar el árbol entero (la comparación es por contenido, no por llamada).
const before = seen.length;
await loadBundle("es");
assert.equal(seen.length, before, "un bundle idéntico re-renderizó de todas formas");

console.log("ok");
