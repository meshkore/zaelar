// V2-481 — EL ARRANQUE EN FRÍO NO PUEDE ENSEÑAR CLAVES.
//
// `t()` cae al bundle inglés y, si tampoco está, muestra la CLAVE. Eso es correcto para una pantalla ya
// cargada —una cadena que falta tiene que verse— y falla justo donde más se nota: en el arranque en frío de
// una Machine, `/api/i18n/bundle` todavía no contesta, así que el PRIMER pantallazo de quien acaba de instalar
// la PWA era `boot.encendiendo`.
//
// Este test enchufa el módulo REAL sin ningún bundle (ni en localStorage ni por red) y exige las dos mitades:
// una clave de arranque sale como TEXTO, y una clave cualquiera sigue saliendo como CLAVE — porque el suelo
// tiene que ser estrecho, o dejaría de verse lo que de verdad falta.
import assert from "node:assert/strict";

const mem = new Map([["hb_lang", "en"]]);            // sin bundle cacheado: instalación NUEVA
globalThis.localStorage = {
  getItem: (k) => (mem.has(k) ? mem.get(k) : null),
  setItem: (k, v) => mem.set(k, String(v)),
  removeItem: (k) => mem.delete(k),
};
globalThis.fetch = async () => { throw new Error("motor todavía dormido"); };   // arranque en frío
globalThis.window = { addEventListener() {}, location: { pathname: "/" } };
globalThis.document = { documentElement: { lang: "" }, addEventListener() {} };

const i18n = await import("../../../../frontend/app/core/i18n.js");

const arranque = i18n.t("boot.encendiendo");
assert.notEqual(arranque, "boot.encendiendo",
  "el arranque en frío volvió a enseñar la clave cruda — es el primer pantallazo del producto");
assert.ok(arranque.length > 3, `el suelo devolvió algo vacío: ${JSON.stringify(arranque)}`);

const cualquiera = i18n.t("debug.col_time");
assert.equal(cualquiera, "debug.col_time",
  "el suelo se ensanchó: una cadena que falta tiene que SEGUIR viéndose como su clave");

console.log("ok");
