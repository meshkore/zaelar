// EL MURO DE CHAT NO PUEDE LLEGAR TARDE (V2-116, sesión b403c979 del 2026-08-18).
//
// Reporte del operador: «el agente me está hablando, no aparece en los subtítulos, no aparece el texto en el chat
// de su respuesta … la respuesta ha tardado más de un minuto desde que yo la he oído por voz hasta que me la has
// colocado en el muro del chat».
//
// Medido en el log durable de esa sesión: la respuesta se GENERA y se pinta en el muro cuando llega el
// `transcript` de LiveKit, que no se emite hasta que el item de conversación se cierra — o sea hasta que el TTS
// ha terminado de hablar la respuesta ENTERA:
//     reply 12:32:13.844 → transcript 12:32:19.267   (5,4 s)
//     reply 12:33:11.376 → transcript 12:33:23.611   (12,2 s)
// El arreglo empuja el texto al muro en cuanto el modelo lo genera, y funde el `transcript` posterior por
// PREFIJO. Esto prueba la pieza pura donde puede fallar sola: el dedup de `pushAgentChat`.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "../../../..");

// ── 1) la costura: sse.js empuja la respuesta al muro en el evento `reply`, sin esperar al transcript ──────────
const sse = readFileSync(path.join(root, "frontend/app/services/sse.js"), "utf8");
const replyBranch = sse.slice(sse.indexOf('/reply/.test'), sse.indexOf('/reply/.test') + 1400);
assert.ok(replyBranch.includes("pushAgentChat"),
  "la rama del `reply` del FlashBrain tiene que empujar el texto al muro YA; si no, el muro vuelve a depender de " +
  "que el TTS acabe de hablar (5-12 s medidos)");
assert.ok(/d\.role === "assistant"/.test(replyBranch),
  "…y solo la del asistente (un `reply` sin role de asistente no es texto que el agente haya dicho)");
// y los SUBTÍTULOS siguen siendo los sincronizados con el audio, no esto
assert.ok(!replyBranch.includes("captionSeg"),
  "los subtítulos NO se alimentan de aquí: van sincronizados con el audio (session-lk.js)");

// ── 2) el dedup por prefijo de pushAgentChat, recortado del store (misma técnica que test_energy_scale.mjs) ────
const store = readFileSync(path.join(root, "frontend/app/core/store.js"), "utf8");
const i = store.indexOf("const _CHAT_MARKERS");
const j = store.indexOf("// Convenience helpers used across services");
assert.ok(i > 0 && j > i, "no encuentro pushAgentChat en store.js — ¿se renombró?");

// se sustituyen las dependencias reactivas por un array plano: lo que se prueba es la REGLA de fusión
const shim = `
let msgs = [];
const setChatMsgs = (fn) => { msgs = fn(msgs); };
const _capChat = (xs) => xs;
${store.slice(i, j)}
export const reset = () => { msgs = []; };
export const push = (role, text) => { msgs = [...msgs, { role, text }]; };
export const dump = () => msgs;
`;
const mod = await import("data:text/javascript," + encodeURIComponent(shim));

// (a) el caso REAL: se pinta al generar, y el transcript idéntico que llega 12 s después NO duplica
mod.reset();
const reply = "Según los resultados, el lanzamiento más destacado de Ferrari en 2026 es el Ferrari F80.";
mod.pushAgentChat(reply);
mod.pushAgentChat(reply);
assert.equal(mod.dump().length, 1, "el transcript posterior no puede duplicar la burbuja");

// (b) barge-in: el transcript llega TRUNCADO → se conserva el texto completo, no dos burbujas
mod.reset();
mod.pushAgentChat(reply);
mod.pushAgentChat("Según los resultados, el lanzamiento");
assert.equal(mod.dump().length, 1, "una locución cortada no puede dejar dos burbujas");
assert.equal(mod.dump()[0].text, reply, "gana el texto COMPLETO (lo que el agente quiso decir)");

// (c) al revés: primero llega un trozo y luego el texto entero → se AMPLÍA en el sitio
mod.reset();
mod.pushAgentChat("Según los resultados");
mod.pushAgentChat(reply);
assert.equal(mod.dump().length, 1);
assert.equal(mod.dump()[0].text, reply, "el texto entero sustituye al parcial ya pintado");

// (d) el relleno de espera (💬, V2-114) NO se funde con la respuesta: son dos cosas dichas de verdad
mod.reset();
mod.pushAgentChat("💬 Espera…");
mod.pushAgentChat(reply);
assert.equal(mod.dump().length, 2, "el relleno y la respuesta son burbujas distintas");

// (e) dos respuestas distintas siguen siendo dos
mod.reset();
mod.pushAgentChat("Son las tres.");
mod.pushAgentChat("Ya te he puesto la música.");
assert.equal(mod.dump().length, 2);

// (f) el marcador 🔔 de notify se sigue normalizando (comportamiento previo, no se rompe)
mod.reset();
mod.pushAgentChat("He creado el widget «X».");
mod.pushAgentChat("🔔 He creado el widget «X».");
assert.equal(mod.dump().length, 1, "🔔 sigue fundiéndose con el mismo texto sin marcador");

console.log("chat wall promptness: OK");
