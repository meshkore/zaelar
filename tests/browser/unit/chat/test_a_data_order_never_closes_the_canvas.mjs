// V2-664 — the CLIENT half: «quita … todas esas entradas de la agenda» must not wipe the desktop.
//
// Measured live 2026-09-11, session eedf7f9b, 09:39:52. Two independent copies of the same rule fired on the
// same sentence — `voice/attention.py::hard_interrupt` on the engine and this fast lane on the client — and
// both read a close verb in one clause plus a bare quantifier fifteen words away in another as «close every
// card». What he was actually ordering was the deletion of ROWS INSIDE the agenda; every widget he had open
// closed instead, twice (the glued fragments re-fired it at 09:39:55).
//
// This drives the REAL `voiceCommands.js`, never a copy of its grammar.
import assert from "node:assert/strict";

// `identifyWidget` reaches the backend; under Node there is none. Only «reloj» ever resolves, and only so
// the dedupe can be reset between cases (see `said`): every assertion below is decided by the close-ALL
// rule alone, which runs before any lookup.
globalThis.fetch = async (url) => ({ json: async () => ({ match: /reloj/.test(url) ? "clock" : null }) });

const { handleWidgetVoice } = await import("../../../../frontend/app/services/voiceCommands.js");

function desk() {
  const calls = [];
  return {
    calls,
    closeAll() { calls.push("closeAll"); },
    close(id) { calls.push("close:" + id); },
    show(id) { calls.push("show:" + id); },
    move(id, w) { calls.push("move:" + id + ":" + w); },
    list() { return []; },
  };
}

// The fast lane dedupes an identical action signature for 2.5 s, and two `closeAll` cases in a row would
// therefore measure the dedupe instead of the rule. Each case is preceded by a DIFFERENT action so the
// signature is never the previous one — the dedupe can suppress a closeAll, never fabricate one.
async function said(text) {
  await handleWidgetVoice(desk(), "abre el reloj", true);    // a different signature, on purpose
  const d = desk();
  await handleWidgetVoice(d, text, true);
  return d.calls;
}

// ── THE MEASURED SENTENCE, exactly as the accumulator glued it ──────────────────────────────────────────
{
  const calls = await said(
    "Vale, quita, por favor, los datos de comidas de la agenda, Veo que varios días tengo asignada la comida," +
    " de la una a las dos, todos esos todas esas entradas de la");
  assert.ok(!calls.includes("closeAll"),
    "an order about rows INSIDE a widget must never close the canvas — this wiped his desktop twice");
}

// ── the class, both directions ──────────────────────────────────────────────────────────────────────────
for (const txt of ["borra todas esas entradas de la agenda",
                   "quita todos los datos de la agenda",
                   "elimina todas las citas de comida"]) {
  const calls = await said(txt);
  assert.ok(!calls.includes("closeAll"), "a quantifier that governs a thing is not the canvas: " + txt);
}

for (const txt of ["cierra todos los widgets",
                   "quita todas las tarjetas",
                   "limpia la pantalla",
                   "close everything"]) {
  const calls = await said(txt);
  assert.ok(calls.includes("closeAll"), "an order about the CARDS must still close them all: " + txt);
}

// ── the counterweights V2-600/V2-647 already bought must not have moved ─────────────────────────────────
{
  const calls = await said("cierra la pantalla completamente");
  assert.ok(!calls.includes("closeAll"), "a fullscreen mention is a screen-state order, never a close-all");
}
{
  const d = desk();
  await handleWidgetVoice(d, "quita todo", false);   // INTERIM
  assert.deepEqual(d.calls, [], "close never acts on a revisable guess — only on the final transcript");
}

console.log("ok — a data order never closes the canvas (4 groups)");
