// LA ESCALA DE LA PILA (EnergyGauge.scale) — contrato de los números que dio el operador el 2026-08-13.
//
// Se prueba en Node y no en un navegador porque `scale` es PURA a propósito: es la única pieza de la pila con
// reglas, así que puede fallar sola, sin DOM, y ahí es donde tiene que fallar.
//
// El problema que resuelve: un saldo crece sin techo y una barra no. La solución son DOS ejes — huecos fijos y el
// VALOR de cada rayita variable, con el color diciendo cuánto vale. Estos casos son literalmente los que pidió el
// operador, y el techo (50 × $5 = $250) es donde puso el límite de lo que tiene sentido recargar.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const src = readFileSync(path.join(here, "../../../../frontend/app/components/EnergyGauge.js"), "utf8");

// Se recorta la función pura: importar el módulo entero arrastraría dom.js/store.js/i18n.js, que necesitan
// navegador. El recorte es honesto — si `scale` deja de existir con ese nombre, esto revienta aquí.
const i = src.indexOf("const SLOTS");
const j = src.indexOf("export function EnergyGauge");
assert.ok(i > 0 && j > i, "no encuentro la escala en EnergyGauge.js — ¿se renombró?");
const mod = await import("data:text/javascript," + encodeURIComponent(src.slice(i, j)));
const { scale } = mod;

const USD = 100;   // 1 Energy = €0,01

// ── los casos que dio el operador, uno por uno ────────────────────────────────────────────────────────────────
// «cuando alguien entra en la demo iluminamos sólo 10»
let s = scale(250, 250);
assert.equal(s.slots, 10, "demo: 10 huecos");
assert.equal(s.lit, 10, "demo recién empezada: llena, no a medias");
assert.equal(s.cls, "eg-demo");
assert.ok(s.demo);

// «cuando alguien paga la cuota de 10 le enchufamos 10 … que representa un dólar cada uno»
s = scale(10 * USD, 10 * USD);
assert.equal(s.slots, 10, "$10: 10 huecos");
assert.equal(s.lit, 10);
assert.equal(s.per, 1 * USD, "$10: cada rayita vale un dólar");
assert.equal(s.cls, "eg-u1", "…y es el color del dólar, NO el de la demo");

// «cuando alguien paga 50 en el mismo color del dólar llenamos los 50»
s = scale(50 * USD, 50 * USD);
assert.equal(s.slots, 50);
assert.equal(s.lit, 50);
assert.equal(s.per, 1 * USD);
assert.equal(s.cls, "eg-u1", "$50 sigue siendo el color del dólar");

// «cuando alguien paga 100 cambiamos el color y usamos rayitas de 2 dólares»
s = scale(100 * USD, 100 * USD);
assert.equal(s.slots, 50, "$100 también cabe en 50 huecos");
assert.equal(s.per, 2 * USD, "$100: rayitas de dos dólares");
assert.equal(s.cls, "eg-u2");

// el TECHO: «ya más de 250 no me tiene sentido que nadie ponga» → 50 × $5, oro
s = scale(250 * USD, 250 * USD);
assert.equal(s.slots, 50);
assert.equal(s.per, 5 * USD);
assert.equal(s.cls, "eg-u5", "$250 es el tope de la escalera: oro");

// ── que la pila se lea como una PILA ─────────────────────────────────────────────────────────────────────────
// EL COLOR SALE DE LA CAPACIDAD, NO DEL SALDO. Si saliera del saldo, el color CAMBIARÍA mientras gastas y dejaría
// de ser una pila: sería un indicador de tramo que va bajando de categoría. Un cliente de $100 casi vacío tiene
// que seguir viéndose como cliente de $100.
const gastando = [100, 60, 20, 1].map(pct => scale(pct / 100 * 100 * USD, 100 * USD));
for (const g of gastando) {
  assert.equal(g.cls, "eg-u2", "el color no se mueve al gastar");
  assert.equal(g.per, 2 * USD);
  assert.equal(g.slots, 50, "los huecos tampoco: lo gastado se queda en gris, no desaparece");
}
assert.deepEqual(gastando.map(g => g.lit), [50, 30, 10, 0], "solo bajan las ENCENDIDAS");

// Y una demo a medias baja de la misma forma
assert.equal(scale(150, 250).lit, 6, "demo con 150 de 250: 6 rayitas de 10");

// ── bordes que no pueden pintar una pila mentirosa ───────────────────────────────────────────────────────────
assert.equal(scale(0, 10 * USD).lit, 0, "a cero: ninguna encendida (y la UI la pinta en rojo)");
assert.equal(scale(-5, 10 * USD).lit, 0, "un saldo negativo no enciende nada");
assert.equal(scale(10, null), null, "sin capacidad no hay pila que dibujar");
assert.equal(scale(10, 0), null);
assert.equal(scale(10, "no-es-un-numero"), null);
// Recargar por encima del techo no desborda la barra ni la deja en blanco.
s = scale(400 * USD, 400 * USD);
assert.equal(s.slots, 50, "por encima de $250 se acota a 50 huecos, no crece sin fin");
assert.equal(s.cls, "eg-u5");
// Nunca se enciende más de lo que hay huecos, ni con un saldo por encima de su capacidad.
assert.ok(scale(999 * USD, 10 * USD).lit <= 50);

console.log("ok — la escala de la pila cumple los casos del operador");
