// V2-481 — COLD START MUST NOT SHOW KEYS.
//
// `t()` falls back to the English bundle and, if that is unavailable too, shows the KEY. That is correct for an already
// loaded screen —a missing string must be visible— and fails precisely where it is most noticeable: during a Machine's
// cold start, `/api/i18n/bundle` has not responded yet, so the FIRST screen seen by someone who has just installed
// the PWA was `boot.encendiendo`.
//
// This test wires in the REAL module without any bundle (neither in localStorage nor over the network) and requires both halves:
// a startup key is returned as TEXT, while an arbitrary key is still returned as the KEY — because the fallback floor
// must be narrow, or genuinely missing content would no longer be visible.
import assert from "node:assert/strict";

const mem = new Map([["hb_lang", "en"]]);            // no cached bundle: NEW installation
globalThis.localStorage = {
  getItem: (k) => (mem.has(k) ? mem.get(k) : null),
  setItem: (k, v) => mem.set(k, String(v)),
  removeItem: (k) => mem.delete(k),
};
globalThis.fetch = async () => { throw new Error("motor todavía dormido"); };   // cold start
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
