// BootOverlay — the first-load splash. Blocks the UI while zaelar boots and plays the «Colmena sináptica»
// animation: a neural constellation that assembles ITSELF IN PARTS (one cluster per boot phase — voz → memoria →
// reflejo) and then, on "listo", implodes into the orb. Phases are driven by REAL signals (store.bootPhase, set by
// session-lk.js from mic/room milestones + the agent's "vl2" boot events); the veil lifts on store.bootReady.
// Only the very first boot shows this — later reconnects never re-lock the UI (a safety timeout unblocks a stuck
// boot; see session-lk.js). The render engine lives in boot-anim.js; this file owns the DOM + wiring.
import { h } from "../core/dom.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import { startBootAnim } from "./boot-anim.js?v=2";

const LABELS = {
  encendiendo: "Encendiendo a zaelar…",
  voz: "Conectando la voz…",
  memoria: "Componiendo la memoria…",
  reflejo: "Afinando el reflejo…",
  listo: "",
};

export function BootOverlay() {
  let canvas;
  const ovl = h("div", { class: () => "boot-ovl" + (store.bootReady() ? " gone" : ""), "aria-hidden": "true" },
    h("canvas", { class: "boot-canvas", ref: el => (canvas = el) }),
    h("div", { class: "boot-caption" }, () => LABELS[store.bootPhase()] || ""),
  );

  // Start the engine once the overlay is in the DOM (ref fires pre-mount, so getBoundingClientRect is 0 then).
  requestAnimationFrame(() => {
    if (!canvas) return;
    const ctrl = startBootAnim(canvas, {
      onDone: () => { ctrl.destroy(); if (ovl.parentNode) ovl.parentNode.removeChild(ovl); },
    });
    // Feed every phase change to the animation (last one, "listo", triggers the implosion).
    createEffect(() => ctrl.setPhase(store.bootPhase()));
  });

  return ovl;
}
