// ============================================================================
// DockBar.js — EVERY control, at the very bottom, ARRANGED AROUND THE ORB.  The mobile counterpart of the desktop's
// «eye» (Orb.js: an arc of 7 icons above the orb) and of the TopBar.
//
// WHY BOTTOM, AND WHY THAT MATTERS FOR LAYOUT: a phone is held in one hand and the thumb reaches the bottom third.
// So this bar is the ONLY chrome with a fixed position in this shell, and its height (--dock-h) is the ONE piece of
// geometry the rest of the shell knows about: every card ends `--dock-h` above the bottom edge so the bar can never
// cover the last line of a widget. On iOS it also pads itself with env(safe-area-inset-bottom), or it would sit
// under the home indicator and every tap would be a swipe-up instead.
//
// ── THE 2026-09-04 RESTYLE (V2-573), operator's brief, verbatim: «icon chat wall, then icon desktop, then in the
// center, the orbe, bigger, with mic icon inside. to the right, config icon». FIVE controls in three zones:
//
//   💬 chat    → store.chatOpen                    the conversation
//   ▤ desk     → the DECK                          the dashboards; closes every sheet and shows the cards
//   ◉  ORB     → the switch (below), 74px, mic INSIDE
//   🎤 mic     → session.toggleMic()               the fifth slot, and the reason it exists is below
//   ⚙ config   → store.mobileMenuOpen              energy · account · voice · settings · feedback
//
// TWO CONTROLS LEFT (2026-09-04), each because the operator's own words retired it:
//   · CAPTIONS. «deactivate subtitles. dont want icon for that» — the button AND the band are gone (the band was
//     also removed from mobile-surfaces.js; the `captionsOn` signal survives untouched for the desktop).
//   · SPEAKER. It moved into the config sheet. It is the one control that can make the agent APPEAR broken, so
//     leaving it one tap from a thumb in a pocket was a trap — and V2-573's own bug is the proof (see below).
//
// WHY THE MIC STAYED WHEN THE SPEAKER DID NOT — the operator asked «and want some other?» and this is the answer:
// silencing your own microphone is a PRIVACY gesture, and a privacy gesture that takes two taps and a sheet is not
// one. The mic glyph inside the orb is the STATE (level while listening, slashed while muted); this button is the
// CONTROL. Same relationship the desktop has between its orb and its arc, so neither shell teaches a second
// vocabulary. If the operator wants four icons instead of five, deleting this block is the whole change.
//
// THE ORB IS THE CENTRE, AND IT IS ALSO THE SWITCH (operator, 2026-08-18: «when stopped there is only the
// on/off button, and when we start it the orb appears; or we touch the orb and it stops»). One slot, two faces:
//
//   agentState() === "off"   →  a ⏻ button. Nothing else can be true about a stopped agent, so nothing else shows.
//   anything else            →  the ORB, live, and tapping it STOPS (or, mid-«pausing», cancels the stop).
//
// That is the same `!store.powerOff()` seam the desktop ⏻ uses — NOT a second one. It matters more here than
// anywhere: since V2-092 the switch is the SERVER's state, so a mobile-only power button that flipped a local
// signal would show "stopped" on the phone while the agent kept working — the exact class of lying state this
// codebase has already paid for once.
//
// THE GLYPHS ARE THE DESKTOP'S, BYTE FOR BYTE (operator: «as similar as possible to those already in the frontend of
// the UI»): MIC/CHAT/PWR are copied from `app/components/Orb.js` so an operator who knows one shell reads the other
// without learning a second vocabulary, and the host-contract test DERIVES that check from Orb.js itself. The two
// additions are MIC_OFF (the desktop only greys a muted mic, which is legible next to six icons on a big screen and
// ambiguous as a lone icon on a phone, so the slash is drawn over the SAME base glyph) and the two glyphs the
// desktop has no twin for: DESK and CFG, drawn in the same vocabulary (24-box, 2px stroke, round caps).
// ============================================================================

import { h, raw } from "../../../app/core/dom.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import * as session from "../../../app/services/session.js?v=3";
import * as api from "../../../app/services/api.js?v=2";
import { t } from "../../../app/core/i18n.js?v=1";
import { OrbMini } from "./OrbMini.js?v=3";

const SW = `viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"`;
const MIC_ON  = `<svg ${SW}><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/></svg>`;
const MIC_OFF = `<svg ${SW}><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/><path d="M4 4l16 16"/></svg>`;
const CHAT    = `<svg ${SW}><path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.4 9.06 9.06 0 0 1-4-.9L3 21l1.9-4.5a8.38 8.38 0 0 1-.9-4A8.5 8.5 0 0 1 12.5 4 8.38 8.38 0 0 1 21 11.5z"/></svg>`;
// DESK — the dashboards. A window split into panes: the deck IS one screen per widget, so the glyph says
// «several screens», not «a grid of apps».
const DESK    = `<svg ${SW}><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18"/><path d="M11 9v11"/></svg>`;
const CFG     = `<svg ${SW}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.65 1.65 0 0 0 15 19.4a1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09A1.65 1.65 0 0 0 15 4.6a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`;
const PWR     = `<svg ${SW}><path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.77.04"/></svg>`;

// BLUE = on/live, pale GREY = off/closed. Same language as the desktop's lid icons.
const cls = (on) => "zm-ic" + (on ? " on" : " off");

// The switch, shared by BOTH faces of the centre slot (the ⏻ button and the orb) so the two can never drift apart.
// Identical to Orb.js's power handler, down to stamping the command BEFORE applying it: without that, a server
// reconciliation that went to fetch the state before this instant tears down the session just asked for (main.js).
function togglePower() {
  const off = !store.powerOff();
  store.markPowerCommand();
  store.setPowerOff(off);
  if (off) {
    try { session.stop(); } catch (_) {}
    api.obsSessionEnd("power_off");
    store.setMicMuted(true); localStorage.setItem("hb_mic_muted", "1");
    store.setBotMuted(true); localStorage.setItem("hb_bot_muted", "1");
    try { store.fetchTasks(); } catch (_) {}
    api.runStop().then(() => store.fetchTasks());
  } else {
    store.setMicMuted(false); localStorage.setItem("hb_mic_muted", "0");
    store.setBotMuted(false); localStorage.setItem("hb_bot_muted", "0");
    try { session.start(); } catch (_) {}
    api.runStart().then(() => store.fetchTasks());
  }
  // Starting the agent is ALSO the best user gesture we will ever get for unlocking audio playback (V2-573): a
  // mobile browser refuses to play a remote track until the page has been touched, and this tap IS that touch.
  try { session.unlockAudio && session.unlockAudio(); } catch (_) {}
  api.uiEvent("mobile:power", { state: off ? "off" : "on" });
}

// The DESK button: the deck is not a sheet, it is what is underneath every sheet, so "show me the dashboards"
// means "close whatever is covering them". With nothing open it is a no-op that still reads as «I am here».
function showDesk() {
  store.setChatOpen(false);
  store.setMobileMenuOpen(false);
  store.setMobileSettingsOpen(false);
  api.uiEvent("mobile:desk", { state: "show" });
}

export function DockBar() {
  // Built ONCE, outside the reactive tree, because the visualiser holds this canvas by reference.
  const ORB = OrbMini();
  return h("nav", { class: "zm-dock", "aria-label": "zaelar controls" },

    // ── LEFT of the orb: the two SURFACES — the conversation, and the dashboards ──
    // These two are the WHOLE footer navigation, no matter how many cards are open (operator, 2026-09-04:
    // «we use only the 2 icons from footer, one for chat one for dashboard, even if we have more than 2
    // opened»). Which card you are on is the deck's business — its pips and its k/n switcher — never the bar's.
    h("div", { class: "zm-side" },
      h("button", {
        class: () => cls(store.chatOpen()),
        "aria-label": () => t("camera.chat_title"),
        onClick: () => { const v = !store.chatOpen(); store.setChatOpen(v); api.uiEvent("mobile:chat", { state: v ? "open" : "close" }); },
      }, raw(CHAT)),

      h("button", {
        // "on" when the deck is what you are looking at: nothing covering it AND something to look at.
        class: () => cls(!store.chatOpen() && !store.mobileMenuOpen() && !store.mobileSettingsOpen()),
        "aria-label": () => t("mobile.dashboards"),
        onClick: showDesk,
      }, raw(DESK)),
    ),

    // ── CENTRE: the orb, which is also the switch. Stopped → a ⏻ and nothing else; running → zaelar's face. ──
    //
    // BOTH faces are built ONCE and swapped by VISIBILITY — deliberately not `() => cond ? a : b`, which is the
    // obvious way to write this and is wrong. A reactive child function re-runs on every agentState change and
    // returns a NEW element tree, so each transition would mint a fresh OrbMini with a fresh <canvas>. main.js
    // hands `$("#orb")` to the visualiser exactly once at boot; after one re-render that reference is a DETACHED
    // node, whose clientWidth is 0, so the render loop keeps running (measured: 741 frames) and paints nothing
    // into a canvas nobody can see, while the canvas actually on screen is never drawn to. Symptom: an empty hole
    // in the middle of the dock, with no error anywhere. Measured 0 painted pixels of 9216 (2026-08-18).
    h("div", { class: "zm-centre" },
      h("button", {
        class: () => "zm-ic zm-pwr pwr-off off" + (store.agentState() === "off" ? "" : " zm-hide"),
        "aria-label": () => t("orb.power_off"),
        onClick: togglePower,
      }, raw(PWR)),
      h("button", {
        // The orb itself. `aria-label` says what a tap DOES, not what the orb is — the state is already
        // announced by OrbMini's own label, and a screen-reader user needs to know this is the stop button.
        // `zm-blocked` is V2-573: the browser is refusing to play audio, so the operator hears nothing while
        // everything else looks healthy. It rides the ORB because that is where someone who cannot hear the
        // agent looks, and tapping it (a gesture) is exactly what the unlock needs.
        class: () => "zm-orb-btn pwr-" + store.agentState()
          + (store.agentState() === "off" ? " zm-hide" : "")
          + (store.audioBlocked() ? " zm-blocked" : ""),
        "aria-label": () => t("mobile.orb_stop"),
        onClick: togglePower,
      }, ORB),
    ),

    // ── RIGHT of the orb: the microphone (privacy, one tap) and everything else ──
    h("div", { class: "zm-side" },
      h("button", {
        class: () => cls(store.agentLive() && !store.micMuted()),
        // The icon IS the level meter (2026-08-10, same request that put the VU on the desktop mic): it scales with
        // the REAL mic RMS through a CSS custom property, so it costs no re-render. With the mic muted or the agent
        // stopped there is no effect, because there is no level — the meter can only move when we are truly hearing.
        style: { "--vu": () => (store.agentLive() && !store.micMuted() ? String(Math.min(1, store.micLevel() * 6)) : "0") },
        "aria-label": () => (store.micMuted() ? t("camera.mic_unmute") : t("camera.mic_mute")),
        onClick: () => { session.toggleMic(); api.uiEvent("mobile:mic", { state: store.micMuted() ? "muted" : "unmuted" }); },
      }, () => raw(store.micMuted() ? MIC_OFF : MIC_ON)),

      h("button", {
        class: () => cls(store.mobileMenuOpen()),
        "aria-label": () => t("mobile.menu"),
        onClick: () => { const v = !store.mobileMenuOpen(); store.setMobileMenuOpen(v); api.uiEvent("mobile:menu", { state: v ? "open" : "close" }); },
      }, raw(CFG)),
    ),
  );
}
