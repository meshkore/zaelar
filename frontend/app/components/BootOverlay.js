// BootOverlay — the first-load splash. Blocks the UI while zaelar boots and plays the «Synaptic hive»
// animation: a neural constellation that assembles ITSELF IN PARTS (one cluster per boot phase — voice → memory →
// reflex) and then, on "ready", implodes into the orb. Phases are driven by REAL signals (store.bootPhase, set by
// session-lk.js from mic/room milestones + the agent's "vl2" boot events); the veil lifts on store.bootReady.
// Only the very first boot shows this — later reconnects never re-lock the UI (a safety timeout unblocks a stuck
// boot; see session-lk.js). The render engine lives in boot-anim.js; this file owns the DOM + wiring.
import { h } from "../core/dom.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import { startBootAnim } from "./boot-anim.js?v=2";
import { t } from "../core/i18n.js?v=1";

// V2-481 — resolve the legend ON EVERY PAINT, not when importing the module.
//
// This used to be a literal object, so `t()` ran ONCE while loading the file — before the bundle
// existed. When the engine finally responded, the legend still said `boot.encendiendo`: the correct
// string arrived and nobody saw it. This is the same defect measured by V2-124 on mobile (a
// `textContent = t()` during construction freezes whatever was available), and here it fails silently — by showing a key.
const LABEL_KEYS = {
  encendiendo: "boot.encendiendo",
  voz: "boot.voz",
  memoria: "boot.memoria",
  reflejo: "boot.reflejo",
  listo: "",
};

function labelFor(phase) {
  const k = LABEL_KEYS[phase];
  return k ? t(k) : "";
}

export function BootOverlay() {
  let canvas;
  const ovl = h("div", { class: () => "boot-ovl" + (store.bootReady() ? " gone" : ""), "aria-hidden": "true" },
    h("canvas", { class: "boot-canvas", ref: el => (canvas = el) }),
    h("div", { class: "boot-caption" }, () => labelFor(store.bootPhase())),
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
