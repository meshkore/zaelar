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

import { h, raw } from "../../../app/core/dom.js?v=2";
import * as store from "../../../app/core/store.js?v=2";

// THE MIC INSIDE THE ORB (V2-573, operator: «the orbe, bigger, with mic icon inside»). It is the STATE, never a
// control — the orb's own tap is the power switch, and the mic BUTTON lives in the dock's right zone.
//
// Built ONCE with BOTH shapes in it and switched by CSS, not by a reactive child: this subtree sits next to the
// two canvases the visualiser holds BY REFERENCE, and re-rendering around them is precisely how the orb ended up
// painting into a detached node in August (see DockBar.js's centre-slot comment). The slash is the same shape the
// dock's MIC_OFF draws, over the same base glyph the desktop's Orb.js defines.
const MIC_IN_ORB = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
  stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"
  ><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"
  /><path class="zm-mic-slash" d="M4 4l16 16"/></svg>`;

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
    h("div", { class: () => "zm-orb-mic" + (store.micMuted() ? " muted" : "") }, raw(MIC_IN_ORB)),
    // The transient "🗣 <voice>" flash after cycling the voice from the menu — the only feedback that it took.
    h("div", { class: () => "zm-vflash" + (store.voiceFlash().show ? " show" : "") }, () => store.voiceFlash().text),
  );
}

// LIVE CAPTIONS — REMOVED FROM THIS SHELL (V2-573, operator: «deactivate subtitles. dont want icon for that»).
// The band used to float just above the dock and had its own 📝 button in the bar; both are gone, and the entry
// in `mobile-surfaces.js` with them. What is NOT touched is `store.captionsOn` / `store.captionSeg`: those are
// the DESKTOP's captions, which still work exactly as before — this is a decision about the phone's screen, not
// about the feature. Re-adding it later is one line in the surfaces list plus a component; the CSS (.zm-cap)
// stays in styles.css, unused and harmless, for that reason.
