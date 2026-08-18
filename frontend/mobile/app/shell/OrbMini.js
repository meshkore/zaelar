// ============================================================================
// OrbMini.js — zaelar's face, shrunk into the CENTRE of the dock.  The desktop's Orb.js is 24 KB because it is also
// the «eye»: an arc of seven controls, an ECG lower lid, a caption teleprompter, a drag handle. None of that survives
// a 76px-tall bar, so this is a fresh component — but it reuses the ENGINE of the desktop orb rather than a copy of it:
//
//   session.startVisuals({ orbCanvas, vizCanvas })
//
// That function takes two <canvas> elements and nothing else (services/visualizer.js reads only the theme and the
// --canvas token; it never queries the DOM for layout). So the animation — zaelar's voice on the orb, the person's
// voice on the spectrum — is literally the same code the desktop runs. If the orb changes there, it changes here.
// That is what makes the operator's «que se mueva cuando la gente nos habla» true by construction rather than by a
// second implementation that would drift.
//
// The canvas keeps the id `orb` deliberately: lib/ecg.js locates it as document.getElementById("orb"), so keeping
// the id means the heartbeat line can be switched on here later without touching that file.
//
// PURELY VISUAL — NO INTERACTION LIVES HERE (changed 2026-08-18). The orb is now the power switch, and its <button>
// is owned by DockBar so that BOTH faces of the centre slot (the ⏻ when stopped, the orb when running) go through
// one handler and cannot drift apart. Nesting a button inside a button is also invalid HTML, and on a phone that
// resolves in whichever way the browser feels like — the outer tap winning on one and the inner on another.
// Cycling the TTS voice moved to a row in the menu sheet, where a deliberate gesture belongs: the one thing that
// must never happen by accident on a phone in a pocket is a gesture that changes what the agent sounds like.
// ============================================================================

import { h } from "../../../app/core/dom.js?v=2";
import * as store from "../../../app/core/store.js?v=2";

export function OrbMini() {
  return h("div", {
    class: () => "zm-orb " + store.agentState() + (store.botSpeaking() ? " talking" : ""),
    // The label is the honest STATE (the wrapping button's own label says what a tap does): a screen reader on a
    // phone is often the only way to know whether anyone is on the other end.
    "aria-label": () => "zaelar: " + store.agentState(),
  },
    // Both canvases are 1:1 with their CSS box; visualizer.js handles DPR itself.
    h("canvas", { id: "orb", class: "zm-orb-c", width: "96", height: "96" }),
    h("canvas", { id: "viz", class: "zm-viz-c", width: "96", height: "96" }),
    // The transient "🗣 <voice>" flash after cycling the voice from the menu — the only feedback that it took.
    h("div", { class: () => "zm-vflash" + (store.voiceFlash().show ? " show" : "") }, () => store.voiceFlash().text),
  );
}

// LIVE CAPTIONS, mobile edition. On the desktop they crawl upward from the orb as a 3-line teleprompter. Here there
// is no room above the orb — the dock is at the very bottom — so they sit as a single band JUST above the dock,
// over whatever card is showing. Same source of truth (store.captionSeg), same on/off signal (store.captionsOn),
// so the 📝 button in the dock and the desktop's 📝 icon control the same thing.
export function CaptionBand() {
  return h("div", {
    class: () => {
      const seg = store.captionSeg();
      const on = store.captionsOn() && !!(seg && seg.text) && store.agentLive();
      return "zm-cap" + (on ? " show" : "");
    },
  }, () => { const s = store.captionSeg(); return s ? s.text : ""; });
}
