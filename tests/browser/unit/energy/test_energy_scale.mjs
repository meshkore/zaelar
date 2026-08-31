// THE STACK SCALE (EnergyGauge.scale) — contract for the numbers provided by the operator on 2026-08-13.
//
// It is tested in Node rather than in a browser because `scale` is deliberately PURE: it is the only piece of the
// stack with rules, so it can fail on its own, without the DOM, and that is where it should fail.
//
// The problem it solves: a balance grows without limit, but a bar does not. The solution is TWO axes — fixed slots and
// the variable VALUE of each tick, with the color indicating how much it is worth. These cases are exactly what the
// operator requested, and the ceiling (50 × $5 = $250) is where they set the limit of what makes sense to recharge.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const src = readFileSync(path.join(here, "../../../../frontend/app/components/EnergyGauge.js"), "utf8");

// The pure function is extracted: importing the entire module would pull in dom.js/store.js/i18n.js, which require a
// browser. The extraction is honest — if `scale` stops existing under that name, this fails here.
const i = src.indexOf("const SLOTS");
const j = src.indexOf("export function EnergyGauge");
assert.ok(i > 0 && j > i, "no encuentro la escala en EnergyGauge.js — ¿se renombró?");
const mod = await import("data:text/javascript," + encodeURIComponent(src.slice(i, j)));
const { scale } = mod;

const USD = 100;   // 1 Energy = €0.01

// ── the cases provided by the operator, one by one ────────────────────────────────────────────────────────────────
// “when someone enters the demo, we light up only 10”
let s = scale(250, 250);
assert.equal(s.slots, 10, "demo: 10 huecos");
assert.equal(s.lit, 10, "demo recién empezada: llena, no a medias");
assert.equal(s.cls, "eg-demo");
assert.ok(s.demo);

// “when someone pays the $10 fee, we plug in 10 … representing one dollar each”
s = scale(10 * USD, 10 * USD);
assert.equal(s.slots, 10, "$10: 10 huecos");
assert.equal(s.lit, 10);
assert.equal(s.per, 1 * USD, "$10: cada rayita vale un dólar");
assert.equal(s.cls, "eg-u1", "…y es el color del dólar, NO el de la demo");

// “when someone pays 50 in the same dollar color, we fill all 50”
s = scale(50 * USD, 50 * USD);
assert.equal(s.slots, 50);
assert.equal(s.lit, 50);
assert.equal(s.per, 1 * USD);
assert.equal(s.cls, "eg-u1", "$50 sigue siendo el color del dólar");

// “when someone pays 100, we change the color and use two-dollar ticks”
s = scale(100 * USD, 100 * USD);
assert.equal(s.slots, 50, "$100 también cabe en 50 huecos");
assert.equal(s.per, 2 * USD, "$100: rayitas de dos dólares");
assert.equal(s.cls, "eg-u2");

// the CEILING: “it no longer makes sense to me for anyone to put in more than 250” → 50 × $5, gold
s = scale(250 * USD, 250 * USD);
assert.equal(s.slots, 50);
assert.equal(s.per, 5 * USD);
assert.equal(s.cls, "eg-u5", "$250 es el tope de la escalera: oro");

// ── make the stack read as a STACK ─────────────────────────────────────────────────────────────────────────
// THE COLOR COMES FROM CAPACITY, NOT THE BALANCE. If it came from the balance, the color would CHANGE as you spend and
// it would stop being a stack: it would be a tier indicator that drops in category. A nearly empty $100 customer must
// continue to look like a $100 customer.
const gastando = [100, 60, 20, 1].map(pct => scale(pct / 100 * 100 * USD, 100 * USD));
for (const g of gastando) {
  assert.equal(g.cls, "eg-u2", "el color no se mueve al gastar");
  assert.equal(g.per, 2 * USD);
  assert.equal(g.slots, 50, "los huecos tampoco: lo gastado se queda en gris, no desaparece");
}
assert.deepEqual(gastando.map(g => g.lit), [50, 30, 10, 0], "solo bajan las ENCENDIDAS");

// A half-filled demo decreases in the same way
assert.equal(scale(150, 250).lit, 6, "demo con 150 de 250: 6 rayitas de 10");

// ── edge cases that must not render a misleading stack ───────────────────────────────────────────────────────────
assert.equal(scale(0, 10 * USD).lit, 0, "a cero: ninguna encendida (y la UI la pinta en rojo)");
assert.equal(scale(-5, 10 * USD).lit, 0, "un saldo negativo no enciende nada");
assert.equal(scale(10, null), null, "sin capacidad no hay pila que dibujar");
assert.equal(scale(10, 0), null);
assert.equal(scale(10, "no-es-un-numero"), null);
// Recharging above the ceiling does not overflow the bar or leave it blank.
s = scale(400 * USD, 400 * USD);
assert.equal(s.slots, 50, "por encima de $250 se acota a 50 huecos, no crece sin fin");
assert.equal(s.cls, "eg-u5");
// It never lights more slots than exist, even with a balance above its capacity.
assert.ok(scale(999 * USD, 10 * USD).lit <= 50);

console.log("ok — la escala de la pila cumple los casos del operador");
