// LA COSECHA EN NÚMEROS: qué se pinta y —sobre todo— qué NO (V2-296, encargo del operador del 2026-08-24).
//
// La pestaña «Proceso» contaba QUÉ estaba haciendo («entrando en es.wallapop.com…») y no CUÁNTO llevaba hecho.
// La rejilla lo dice. Lo que se prueba aquí no es que pinte, es que sepa CALLARSE, que es donde una rejilla de
// cifras miente:
//   · `{}` es «no lo sabemos» y NO es «cero». Una rejilla de ceros afirma que se miró y no había nada, que es
//     justo lo contrario de no haber mirado todavía.
//   · un PILAR en cero sí se pinta: «0 fichas leídas» distingue una página que no dio nada de una que nadie
//     leyó, y esa diferencia es la que explica un resultado vacío.
//   · un DESCARTE en cero no se pinta: «0 repetidas» ocupa el mismo sitio que una cifra que dice algo, y en una
//     tarjeta estrecha ese sitio es lo único que hay.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(here, "../../../..");
const src = readFileSync(path.join(root, "widgets/results/widget.js"), "utf8");

// Se recorta el TROZO REAL del widget —`TALLY` y `paintHarvest` tal cual están— en vez de reescribir la regla
// aquí. Un test que reimplementa lo que mide pasa siempre: mide su propia copia.
const i = src.indexOf("const TALLY = [");
const j = src.indexOf("function paintProcess(");
assert.ok(i > 0 && j > i, "no encuentro TALLY/paintHarvest en widgets/results/widget.js — ¿se renombró?");

// DOM mínimo: lo que se mide es el ÁRBOL que sale, así que basta con nodos que sepan decir su clase y su texto.
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

// ── 1) «no lo sabemos» no se pinta ──────────────────────────────────────────────────────────────────────────
for (const nada of [{}, null, undefined]) {
  assert.equal(pintar(nada).length, 0,
    "sin cosecha no se pinta rejilla: una fila de ceros AFIRMA que se miró y no había, y todavía no se ha mirado");
}

// El orden de estos dos bloques NO es cosmético: el caso de los pilares lleva descartes en cero, así que si
// alguien deja de suprimirlos ese caso también se pone rojo — y con el mensaje de los pilares, que no nombra el
// defecto. Comprobar primero la supresión hace que cada avería se explique sola.
// ── 2) un descarte en cero NO ocupa sitio ───────────────────────────────────────────────────────────────────
const limpia = pintar({pages: 3, rows: 40, repeated: 0, unnamed: 0, hollow: 0, kept: 40, offered: 3});
const etiquetas = limpia.map(c => c.label);
for (const descarte of ["repetidas", "sin nombre", "sin precio ni tel."]) {
  assert.ok(!etiquetas.includes(descarte),
    `«0 ${descarte}» ocupa el mismo sitio que una cifra que dice algo, y en una tarjeta estrecha ese sitio es ` +
    "lo único que hay");
}
assert.deepEqual(etiquetas, ["páginas miradas", "fichas leídas", "candidatos", "en la conversación"]);

// ── 3) los pilares se pintan aunque valgan cero ─────────────────────────────────────────────────────────────
const vacia = pintar({pages: 0, rows: 0, kept: 0});
assert.deepEqual(vacia.map(c => c.label), ["páginas miradas", "fichas leídas", "candidatos"],
  "los tres pilares se pintan SIEMPRE: «0 fichas leídas» es lo que separa una página que no dio nada de una " +
  "que nadie llegó a leer, y sin esa diferencia un resultado vacío no tiene explicación");
assert.ok(vacia.every(c => c.n === "0" && c.dim),
  "un pilar en cero se pinta apagado: está, pero no compite con las cifras que sí dicen algo");

// ── 4) el embudo se lee en orden, y de arriba abajo cuadra ──────────────────────────────────────────────────
const real = pintar({pages: 3, rows: 40, repeated: 9, unnamed: 4, hollow: 5, kept: 22, offered: 3});
assert.deepEqual(real.map(c => c.label),
  ["páginas miradas", "fichas leídas", "repetidas", "sin nombre", "sin precio ni tel.", "candidatos",
   "en la conversación"],
  "el orden ES la explicación: cuánto se miró → qué se recogió → qué se cayó en cada corte → qué queda → qué " +
  "llegó a la conversación. Cambiarlo deja las cifras y se lleva el porqué");
assert.ok(real.every(c => !c.dim), "con cifras de verdad no hay ninguna apagada");

// El embudo tiene que cerrar: lo leído menos lo descartado es lo que queda.
const h = {pages: 3, rows: 40, repeated: 9, unnamed: 4, hollow: 5, kept: 22, offered: 3};
assert.equal(h.rows - h.repeated - h.unnamed - h.hollow, h.kept,
  "el ejemplo del test no cuadra: si los cortes no suman, la rejilla enseña una resta que no cierra");

// ── 5) el embudo se lee como una RESTA, no como cinco cifras sueltas ────────────────────────────────────────
// Esto salió de RENDERIZARLO, no de leerlo: la geometría estaba bien a los cinco anchos (nada recortado, nada
// desbordado, reflujo limpio 6→3→2 columnas) y la captura seguía leyéndose mal. Siete cajas iguales convierten
// una resta en cinco estadísticas independientes. El orden lo explicaba, y el orden NO sobrevive al reflujo: a
// 360 px la rejilla cae a dos columnas y «22 candidatos» aterriza al lado de «5 sin precio» como si fuera su par.
const conSigno = Object.fromEntries(real.map(c => [c.label, c.n]));
assert.equal(conSigno["repetidas"], "\u22129",
  "un descarte tiene que verse como lo que es —una resta—; sin signo, «9 repetidas» se lee como un hallazgo más");
assert.equal(conSigno["sin nombre"], "\u22124");
assert.equal(conSigno["sin precio ni tel."], "\u22125");

assert.equal(conSigno["fichas leídas"], "40", "un pilar NO lleva signo: es el total del que se resta");
assert.equal(conSigno["candidatos"], "22", "lo que sobrevive tampoco: es el resultado de la resta");
assert.equal(conSigno["en la conversación"], "3",
  "«en la conversación» no es un descarte sino una SELECCIÓN de los candidatos — restarlo diría que se perdieron 3");

// …y es el MENOS de verdad (U+2212), no un guion: un guion no cuadra con las cifras y se lee como raya.
assert.ok(!real.some(c => c.n.startsWith("-")), "es U+2212 MINUS SIGN, no un hyphen-minus");

// La clase marca la fila para el CSS que la hunde. Sin ella el signo va solo y compite en peso con los totales.
const cortes = real.filter(c => c.cut).map(c => c.label);
assert.deepEqual(cortes, ["repetidas", "sin nombre", "sin precio ni tel."],
  "solo los descartes se hunden: hundir un pilar escondería justo la cifra que explica el resultado");

console.log("ok");
