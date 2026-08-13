// EnergyGauge — LA PILA. Cuánta Energy le queda a la cuenta, a la izquierda del 👤 de la barra superior.
//
// Nace de una queja concreta (operador, 2026-08-13): el agente se quedó sin energía a mitad de trabajo y se enteró
// por un cartel, sin haber visto NUNCA cuánta le quedaba. Es la misma clase de fallo que un agente caído que se
// pinta vivo: un estado que puede dejarte tirado tiene que VERSE antes, no anunciarse después.
//
// SOLO CLOUD. En self-host `/api/energy` devuelve `cloud:false` y aquí no se pinta nada — no hay saldo que gastar,
// el usuario paga sus propias APIs.
//
// ── LA ESCALA ────────────────────────────────────────────────────────────────────────────────────────────────
// El problema de dibujar un saldo es que crece sin techo y una barra no. Se resuelve con DOS ejes en vez de uno:
// la pila tiene un número FIJO de huecos y lo que cambia es **cuánto vale cada rayita**, con el color diciendo
// cuánto vale. Así un saldo pequeño y uno 25 veces mayor caben en el mismo sitio, y quien tiene más lo VE (más
// rayitas encendidas, y las de los dos tramos altos son más anchas).
//
//   valor por rayita = techo(capacidad / 50 huecos), acotado a la escalera de tramos
//   rayitas encendidas = saldo / valor · huecos dibujados = los que había al empezar
//
// **La CAPACIDAD fija el valor y el color, no el saldo.** Si dependiera del saldo, el color cambiaría mientras
// gastas y la pila dejaría de leerse como una pila: sería un indicador de tramo bajando de categoría.
//
// Una capacidad por debajo del escalón más bajo de la escalera × 10 no puede venir de una recarga (no hay recarga
// tan pequeña): es una asignación inicial, y se dibuja en su propia banda de 10 huecos con su color. Por eso la
// pila NO necesita que nadie le diga el plan de la cuenta — le basta el saldo y de cuánto se partía.
//
// El techo de la escalera (50 huecos × el escalón más alto) es deliberado: por encima de eso la pila se acota en
// vez de crecer, porque una barra que llega al borde de la pantalla ya no informa de nada.
//
// Y lo gastado NO desaparece: se queda en gris pálido. Sin eso no es una pila, es un número de rayitas variable —
// no se vería que se está agotando, que es justo lo que hay que ver.
import { h } from "../core/dom.js?v=2";
import * as store from "../core/store.js?v=2";
import { t } from "../core/i18n.js?v=1";

const SLOTS = 50;                 // huecos de la pila LLENA
const DEMO_SLOTS = 10;            // los de un grant de demo (banda propia: no es una compra)
const ENERGY_PER_USD = 100;       // 1 Energy = €0,01 (nucleo/energy_meter.EUR_PER_ENERGY_UNIT)

// La escalera. `usd` = lo que vale una rayita; `cls` = su color en styles.css. Ascendente en valor percibido:
// verde (sano) → naranja → los tres metales. Verde→amarillo→naranja como SUBIDA leería como que empeora, que es lo
// contrario de lo que cuenta un tramo más alto.
const LADDER = [
  { usd: 1, cls: "eg-u1" },       // verde
  { usd: 2, cls: "eg-u2" },       // naranja
  { usd: 3, cls: "eg-u3" },       // bronce
  { usd: 4, cls: "eg-u4" },       // plata — rayita más ancha
  { usd: 5, cls: "eg-u5" },       // oro   — rayita más ancha
];
const DEMO = { cls: "eg-demo" };  // ámbar

/** Saldo + capacidad (en Energy) → cómo se dibuja la pila. PURA: es la única pieza con reglas, así que se puede
 *  probar sin DOM (tests/browser). Devuelve `null` cuando no hay nada que pintar. */
export function scale(balance, capacity) {
  const cap = Number(capacity);
  if (!Number.isFinite(cap) || cap <= 0) return null;
  const bal = Math.max(0, Number.isFinite(Number(balance)) ? Number(balance) : 0);
  const capUsd = cap / ENERGY_PER_USD;
  if (capUsd < LADDER[0].usd * DEMO_SLOTS) {
    // BANDA DEMO: la pila entera son 10 rayitas del tamaño del grant, no de un dólar — un grant de $2,50 tiene que
    // verse LLENO al empezar (10 de 10), no como una cuota a medias (2 de 10), que diría algo falso.
    const per = cap / DEMO_SLOTS;
    return { slots: DEMO_SLOTS, per, cls: DEMO.cls, demo: true,
             lit: Math.min(DEMO_SLOTS, Math.floor(bal / per)) };
  }
  const step = LADDER.find(s => capUsd <= s.usd * SLOTS) || LADDER[LADDER.length - 1];
  const per = step.usd * ENERGY_PER_USD;
  return { slots: Math.min(SLOTS, Math.max(1, Math.round(cap / per))), per, cls: step.cls, demo: false,
           lit: Math.min(SLOTS, Math.floor(bal / per)) };
}

export function EnergyGauge() {
  return () => {
    const e = store.energy() || {};
    if (!e.cloud) return null;                       // self-host: no hay pila que pintar
    // NO SABERLO Y ESTAR A CERO NO PUEDEN VERSE IGUAL. Mientras la cuenta no haya gastado nada no tenemos saldo
    // (llega en la respuesta de cada reporte de consumo), así que se pinta una pila APAGADA con su aviso, nunca
    // una vacía — que diría «se te ha acabado» sin que sea verdad.
    if (!e.known) {
      return h("div", { class: "eg eg-unknown", title: () => t("energy.unknown") },
        ...Array.from({ length: DEMO_SLOTS }, () => h("i", { class: "eg-t eg-off" })));
    }
    const s = scale(e.balance, e.capacity);
    if (!s) return null;
    const bal = Math.max(0, Math.round(Number(e.balance) || 0));
    const tip = t(s.lit ? "energy.tip" : "energy.empty")
      .replace("{balance}", String(bal))
      .replace("{per}", String(Math.round(s.per)))
      .replace("{lit}", String(s.lit))
      .replace("{slots}", String(s.slots));
    return h("div", { class: "eg " + s.cls + (s.lit ? "" : " eg-dead"), title: tip },
      // Las rayitas se pintan de IZQUIERDA a DERECHA y se gastan por la DERECHA (la más cercana al 👤 cae primero),
      // así el frente de consumo queda junto al icono de la cuenta, que es donde se va a mirar.
      ...Array.from({ length: s.slots }, (_, i) =>
        h("i", { class: "eg-t" + (i < s.lit ? "" : " eg-spent") })));
  };
}
