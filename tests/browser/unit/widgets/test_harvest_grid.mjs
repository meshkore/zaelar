// HARVEST IN NUMBERS: what gets rendered and —above all— what does NOT (V2-296, operator request from 2026-08-24).
//
// The «Proceso» tab reported WHAT it was doing («entering es.wallapop.com…») rather than HOW MUCH it had done.
// The grid says that. What is tested here is not whether it renders, but whether it knows how to KEEP QUIET,
// which is where a grid of figures lies:
//   · `{}` means «we don't know» and is NOT «zero». A grid of zeroes claims that it was checked and there was
//     nothing there, which is precisely the opposite of not having checked yet.
//   · a zero-valued PILLAR is rendered: «0 fichas leídas» distinguishes a page that yielded nothing from one that
//     nobody read, and that difference is what explains an empty result.
//   · a zero-valued REJECTION is not rendered: «0 repetidas» takes the same space as a figure that says something,
//     and on a narrow card that space is all there is.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "../../../..");
const src = readFileSync(path.join(root, "widgets/results/widget.js"), "utf8");

// The widget's ACTUAL SNIPPET —`TALLY` and `paintHarvest` exactly as they are— is extracted instead of rewriting
// the rule here. A test that reimplements what it measures always passes: it measures its own copy.
const i = src.indexOf("const TALLY = [");
const j = src.indexOf("function paintProcess(");
assert.ok(i > 0 && j > i, "no encuentro TALLY/paintHarvest en widgets/results/widget.js — ¿se renombró?");

// Minimal DOM: what is measured is the resulting TREE, so nodes only need to expose their class and text.
const shim = `
const mk = (tag) => ({
  tag, className: "", textContent: "", childNodes: [],
  appendChild(c){ this.childNodes.push(c); return c; },
});
const document = { createElement: mk };
function elem(tag, cls, text){
  const e = document.createElement(tag);
  if(cls) e.className = cls;
  if(text != null) e.textContent = String(text);
  return e;
}
${src.slice(i, j)}
export { TALLY, paintHarvest };
export const panel = () => mk("div");
`;
const mod = await import("data:text/javascript," + encodeURIComponent(shim));

const pintar = (harvest) => {
  const p = mod.panel();
  mod.paintHarvest(p, harvest);
  const grid = p.childNodes[0];
  if (!grid) return [];
  return grid.childNodes.map(box => ({
    n: box.childNodes[0].textContent,
    label: box.childNodes[1].textContent,
    dim: /\bdim\b/.test(box.className),
    cut: /\bcut\b/.test(box.className),
  }));
};

// ── 1) «we don't know» is not rendered ──────────────────────────────────────────────────────────────────────
for (const nada of [{}, null, undefined]) {
  assert.equal(pintar(nada).length, 0,
    "sin cosecha no se pinta rejilla: una fila de ceros AFIRMA que se miró y no había, y todavía no se ha mirado");
}

// The order of these two blocks is NOT cosmetic: the pillar case has zero rejections, so if someone stops
// suppressing them that case also turns red — and with the pillar message, which does not name the defect.
// Checking suppression first makes each failure explain itself.
// ── 2) a zero rejection takes NO space ─────────────────────────────────────────────────────────────────────
const limpia = pintar({pages: 3, rows: 40, repeated: 0, unnamed: 0, hollow: 0, kept: 40, offered: 3});
const etiquetas = limpia.map(c => c.label);
for (const descarte of ["repetidas", "sin nombre", "sin precio ni tel."]) {
  assert.ok(!etiquetas.includes(descarte),
    `«0 ${descarte}» ocupa el mismo sitio que una cifra que dice algo, y en una tarjeta estrecha ese sitio es ` +
    "lo único que hay");
}
assert.deepEqual(etiquetas, ["páginas miradas", "fichas leídas", "candidatos", "en la conversación"]);

// ── 3) pillars are rendered even when their value is zero ───────────────────────────────────────────────────
const vacia = pintar({pages: 0, rows: 0, kept: 0});
assert.deepEqual(vacia.map(c => c.label), ["páginas miradas", "fichas leídas", "candidatos"],
  "los tres pilares se pintan SIEMPRE: «0 fichas leídas» es lo que separa una página que no dio nada de una " +
  "que nadie llegó a leer, y sin esa diferencia un resultado vacío no tiene explicación");
assert.ok(vacia.every(c => c.n === "0" && c.dim),
  "un pilar en cero se pinta apagado: está, pero no compite con las cifras que sí dicen algo");

// ── 4) the funnel reads in order, and adds up from top to bottom ────────────────────────────────────────────
const real = pintar({pages: 3, rows: 40, repeated: 9, unnamed: 4, hollow: 5, kept: 22, offered: 3});
assert.deepEqual(real.map(c => c.label),
  ["páginas miradas", "fichas leídas", "repetidas", "sin nombre", "sin precio ni tel.", "candidatos",
   "en la conversación"],
  "el orden ES la explicación: cuánto se miró → qué se recogió → qué se cayó en cada corte → qué queda → qué " +
  "llegó a la conversación. Cambiarlo deja las cifras y se lleva el porqué");
assert.ok(real.every(c => !c.dim), "con cifras de verdad no hay ninguna apagada");

// The funnel must close: what was read minus what was rejected is what remains.
const h = {pages: 3, rows: 40, repeated: 9, unnamed: 4, hollow: 5, kept: 22, offered: 3};
assert.equal(h.rows - h.repeated - h.unnamed - h.hollow, h.kept,
  "el ejemplo del test no cuadra: si los cortes no suman, la rejilla enseña una resta que no cierra");

// ── 5) the funnel reads as a SUBTRACTION, not as five separate figures ─────────────────────────────────────
// This came from RENDERING IT, not from reading it: the geometry was fine at all five widths (nothing clipped,
// nothing overflowing, clean 6→3→2-column reflow), and the screenshot still read badly. Seven identical boxes
// turn a subtraction into five independent statistics. The order explained it, and the order does NOT survive
// reflow: at 360 px the grid drops to two columns and «22 candidatos» lands beside «5 sin precio» as if they
// were a pair.
const conSigno = Object.fromEntries(real.map(c => [c.label, c.n]));
assert.equal(conSigno["repetidas"], "\u22129",
  "un descarte tiene que verse como lo que es —una resta—; sin signo, «9 repetidas» se lee como un hallazgo más");
assert.equal(conSigno["sin nombre"], "\u22124");
assert.equal(conSigno["sin precio ni tel."], "\u22125");

assert.equal(conSigno["fichas leídas"], "40", "un pilar NO lleva signo: es el total del que se resta");
assert.equal(conSigno["candidatos"], "22", "lo que sobrevive tampoco: es el resultado de la resta");
assert.equal(conSigno["en la conversación"], "3",
  "«en la conversación» no es un descarte sino una SELECCIÓN de los candidatos — restarlo diría que se perdieron 3");

// …and it is the real MINUS SIGN (U+2212), not a hyphen: a hyphen does not align with the figures and reads as a dash.
assert.ok(!real.some(c => c.n.startsWith("-")), "es U+2212 MINUS SIGN, no un hyphen-minus");

// The class marks the row for the CSS that sinks it. Without it, the sign stands alone and competes in weight with the totals.
const cortes = real.filter(c => c.cut).map(c => c.label);
assert.deepEqual(cortes, ["repetidas", "sin nombre", "sin precio ni tel."],
  "solo los descartes se hunden: hundir un pilar escondería justo la cifra que explica el resultado");

console.log("ok");
