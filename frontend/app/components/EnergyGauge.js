// EnergyGauge — THE BATTERY. How much Energy remains in the account, left of the 👤 in the top bar.
//
// Born from a concrete complaint (operator, 2026-08-13): the agent ran out of energy halfway through a task and learned it
// from a banner, having NEVER seen how much remained. It is the same kind of failure as a down agent painted as alive:
// a state that can strand you must be VISIBLE beforehand, not announced afterward.
//
// CLOUD ONLY. On self-host, `/api/energy` returns `cloud:false` and nothing is rendered here — there is no balance to spend;
// the user pays for their own APIs.
//
// ── LA ESCALA ────────────────────────────────────────────────────────────────────────────────────────────────
// The problem with drawing a balance is that it grows without bound while a bar does not. Solve it with TWO axes:
// the battery has a FIXED number of slots, and what changes is **the value of each tick**, indicated by its color.
// This lets a small balance and one 25 times larger fit in the same space, while the larger balance remains VISIBLE
// through more lit ticks; ticks in the two upper tiers are wider.
//
//   value per tick = ceiling(capacity / 50 slots), bounded by the tier ladder
//   lit ticks = balance / value · rendered slots = the number present at startup
//
// **CAPACITY fixes the value and color, not the balance.** If it depended on the balance, the color would change as
// you spend and the battery would stop reading as a battery: it would be a tier indicator dropping in rank.
//
// Capacity below the ladder's lowest tier × 10 cannot come from a top-up (there is no top-up that small): it is an
// initial grant, drawn in its own 10-slot band with its color. The battery therefore does NOT need the account plan;
// it only needs the balance and the starting capacity.
//
// The ladder ceiling (50 slots × the highest tier) is deliberate: above it the battery is capped instead of growing,
// because a bar reaching the edge of the screen no longer conveys information.
//
// Spent capacity does NOT disappear: it remains pale gray. Without that, this is not a battery but a variable number
// of ticks; you could not see it being depleted, which is exactly what must be visible.
import { h } from "../core/dom.js?v=2";
import * as store from "../core/store.js?v=2";
import { t } from "../core/i18n.js?v=1";

const SLOTS = 50;                 // huecos de la pila LLENA
const DEMO_SLOTS = 10;            // los de un grant de demo (banda propia: no es una compra)
const ENERGY_PER_USD = 100;       // 1 Energy = €0,01 (nucleo/energy_meter.EUR_PER_ENERGY_UNIT)

// The ladder. `usd` = the value of one tick; `cls` = its color in styles.css. Ascending in perceived value:
// green (healthy) → orange → the three metals. Green→yellow→orange as an ASCENT would read as worsening, the
// opposite of what a higher tier means.
const LADDER = [
  { usd: 1, cls: "eg-u1" },       // verde
  { usd: 2, cls: "eg-u2" },       // naranja
  { usd: 3, cls: "eg-u3" },       // bronce
  { usd: 4, cls: "eg-u4" },       // silver — wider tick
  { usd: 5, cls: "eg-u5" },       // gold   — wider tick
];
const DEMO = { cls: "eg-demo" };  // amber

/** Balance + capacity (in Energy) → how to draw the battery. PURE: the only piece containing rules, so it can be
 * tested without the DOM (tests/browser). Returns `null` when there is nothing to render. */
export function scale(balance, capacity) {
  const cap = Number(capacity);
  if (!Number.isFinite(cap) || cap <= 0) return null;
  const bal = Math.max(0, Number.isFinite(Number(balance)) ? Number(balance) : 0);
  const capUsd = cap / ENERGY_PER_USD;
  if (capUsd < LADDER[0].usd * DEMO_SLOTS) {
    // DEMO BAND: the entire battery is 10 grant-sized ticks, not dollar-sized — a $2.50 grant must
    // appear FULL at the start (10 of 10), not as a half quota (2 of 10), which would be misleading.
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
    if (!e.cloud) return null;                       // self-host: there is no battery to render
    // NO SABERLO Y ESTAR A CERO NO PUEDEN VERSE IGUAL. Mientras la cuenta no haya gastado nada no tenemos saldo
    // (it arrives in each usage-report response), so render an OFF battery with its notice, never
    // an empty one — that would say "you are out" when it is not true.
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
      // Ticks are rendered from LEFT to RIGHT and spent from the RIGHT (the one nearest 👤 falls first),
      // keeping the consumption front beside the account icon, where users look.
      ...Array.from({ length: s.slots }, (_, i) =>
        h("i", { class: "eg-t" + (i < s.lit ? "" : " eg-spent") })));
  };
}
