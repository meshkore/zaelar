// ============================================================================
// OrbMini.js — zaelar's face, shrunk into the dock.  The desktop's Orb.js is 24 KB because it is also the «eye»:
// an arc of seven controls, an ECG lower lid, a caption teleprompter, a drag handle. None of that survives a
// 64px-tall bar, so this is a fresh component — but it reuses the ENGINE of the desktop orb rather than a copy of it:
//
//   session.startVisuals({ orbCanvas, vizCanvas })
//
// That function takes two <canvas> elements and nothing else (services/visualizer.js reads only the theme and the
// --canvas token; it never queries the DOM for layout). So the animation — zaelar's voice on the orb, the person's
// voice on the spectrum — is literally the same code the desktop runs. If the orb changes there, it changes here.
//
// The canvas keeps the id `orb` deliberately: lib/ecg.js locates it as document.getElementById("orb"), so keeping
// the id means the heartbeat line can be switched on here later without touching that file.
//
// TAP = cycle voice, the same gesture as tapping the desktop orb. A LONG PRESS is deliberately NOT bound: the one
// gesture that must never happen by accident on a phone in a pocket is a gesture that changes what the agent is.
// ============================================================================

import { h } from "../../../app/core/dom.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import * as session from "../../../app/services/session.js?v=3";
import * as api from "../../../app/services/api.js?v=2";

export function OrbMini() {
  return h("div", {
    class: () => "zm-orb " + store.agentState() + (store.botSpeaking() ? " talking" : ""),
    // The label is the honest state, not decoration: a screen reader on a phone is often the only way to know
    // whether anyone is on the other end.
    role: "button",
    "aria-label": () => "zaelar: " + store.agentState(),
    onClick: () => { session.cycleVoice(); api.uiEvent("mobile:orb", { action: "cycle_voice" }); },
  },
    // Both canvases are 1:1 with their CSS box; visualizer.js handles DPR itself.
    h("canvas", { id: "orb", class: "zm-orb-c", width: "96", height: "96" }),
    h("canvas", { id: "viz", class: "zm-viz-c", width: "96", height: "96" }),
    // The transient "🗣 <voice>" flash after a tap — the only feedback that the tap did anything.
    h("div", { class: () => "zm-vflash" + (store.voiceFlash().show ? " show" : "") }, () => store.voiceFlash().text),
  );
}

// LIVE CAPTIONS, mobile edition. On the desktop they crawl upward from the orb as a 3-line teleprompter. Here there
// is no room above the orb — the dock is at the very bottom — so they sit as a single band JUST above the dock,
// over whatever card is showing. Same source of truth (store.captionSeg), same on/off signal (store.captionsOn),
// so the ⚙ toggle in the mobile settings sheet and the desktop's 📝 icon control the same thing.
export function CaptionBand() {
  return h("div", {
    class: () => {
      const seg = store.captionSeg();
      const on = store.captionsOn() && !!(seg && seg.text) && store.agentLive();
      return "zm-cap" + (on ? " show" : "");
    },
  }, () => { const s = store.captionSeg(); return s ? s.text : ""; });
}
