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
// ── THE COMPOSITION (2026-10-24, operator): SEVEN controls around the orb, three a side plus feedback.
//
//   ☰ menu     → store.mobileMenuOpen              account · energy · settings · voice · desktop
//   💬 chat    → store.chatOpen                    the conversation
//   🤖 wake    → attention_mode                    the wake word, the desktop orb's 🤖
//   ◉  ORB     → the switch (below), 74px, mic INSIDE
//   🎤 mic     → session.openMicHere / mic.toggle  opening it takes the voice to this device
//   🔊 speaker → session.openSpeakerHere / toggle  same rule
//   ⚠ feedback → store.mobileFeedbackOpen          its own sheet (FeedbackSheet.js)
//
// The 2026-09-04 dashboards button is gone: the deck's own navigation is the PIPS above this bar and the side
// swipe. The speaker, moved to the config sheet in V2-573, is back here because the voice now belongs to ONE device
// and the hand that opens mic or speaker is what takes it there. Captions stay out (V2-573).
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
// desktop has no twin for: MENU, drawn in the same vocabulary (24-box, 2px stroke, round caps).
// ============================================================================

import { h, raw } from "../../../app/core/dom.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import * as session from "../../../app/services/session.js?v=3";
import * as api from "../../../app/services/api.js?v=2";
import * as mic from "../../../app/services/mic.js?v=1";
import { t } from "../../../app/core/i18n.js?v=1";
import { OrbMini } from "./OrbMini.js?v=3";
import * as power from "../../../app/services/power.js?v=1";

const SW = `viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"`;
const MIC_ON  = `<svg ${SW}><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/></svg>`;
const MIC_OFF = `<svg ${SW}><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/><path d="M4 4l16 16"/></svg>`;
const CHAT    = `<svg ${SW}><path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.4 9.06 9.06 0 0 1-4-.9L3 21l1.9-4.5a8.38 8.38 0 0 1-.9-4A8.5 8.5 0 0 1 12.5 4 8.38 8.38 0 0 1 21 11.5z"/></svg>`;
// SPEAKER and the WAKE WORD (2026-10-24) are the desktop's drawings, byte for byte (Orb.js SPK_ON/SPK_OFF/BOT_ICON).
const SPK_ON  = `<svg ${SW}><path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M18.5 5.5a9 9 0 0 1 0 13"/></svg>`;
const SPK_OFF = `<svg ${SW}><path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="m22 9-6 6"/><path d="m16 9 6 6"/></svg>`;
// FEEDBACK — a SQUARE bubble with «!», so it never reads as the round chat bubble beside it.
const FB      = `<svg ${SW}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><path d="M12 7v4"/><path d="M12 14h.01"/></svg>`;
const BOT     = `<svg ${SW}><path d="M12 8V4H8"/><rect x="4" y="8" width="16" height="12" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M9 13v2"/><path d="M15 13v2"/></svg>`;
// MENU (2026-10-25, operator): the main menu is the classic three bars — a gear promised «settings» and opened the
// account, the energy and everything else; settings are now one row inside it.
const MENU    = `<svg ${SW}><path d="M4 7h16"/><path d="M4 12h16"/><path d="M4 17h16"/></svg>`;
const PWR     = `<svg ${SW}><path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.77.04"/></svg>`;

// BLUE = on/live, pale GREY = off/closed. Same language as the desktop's lid icons.
const cls = (on) => "zm-ic" + (on ? " on" : " off");

// The switch, shared by BOTH faces of the centre slot (the ⏻ button and the orb) so the two can never drift apart.
// Identical to Orb.js's power handler, down to stamping the command BEFORE applying it: without that, a server
// reconciliation that went to fetch the state before this instant tears down the session just asked for (main.js).
// V2-792 §9 — switching the agent on/off and the centre tap live in ONE door both shells use
// (`app/services/power.js`). This file used to start the voice session BEFORE the server had the switch on, so the
// server refused it and the phone sat «off» over a running agent (2026-10-25 22:40:17).

// THE WAKE WORD, same switch as the desktop orb's 🤖 (Orb.js): ON = `smart` (say the name once, keep talking),
// OFF = `always`. Written through the same /api/settings seam; the SSE `orb:attention` event keeps both shells in step.
const wakeOn = () => store.attentionMode() === "smart" || store.attentionMode() === "wakeword";
function toggleWake() {
  const prev = store.attentionMode();
  const next = wakeOn() ? "always" : "smart";
  store.setAttentionMode(next);
  api.saveSettings({ attention_mode: next }).catch(() => store.setAttentionMode(prev));
  api.uiEvent("mobile:attention", { state: next });
}

export function DockBar() {
  // The wake-word state and the name are read once here, as the desktop orb does; SSE keeps them live afterwards.
  api.getSettings().then((cfg) => {
    const knob = (cfg.knobs || []).find((k) => k.key === "attention_mode");
    if (knob) store.setAttentionMode(knob.value === "wakeword" ? "smart" : knob.value);
    if (cfg.assistant_name) store.setAssistantName(cfg.assistant_name);
  }).catch(() => {});
  // Built ONCE, outside the reactive tree, because the visualiser holds this canvas by reference.
  const ORB = OrbMini();
  return h("nav", { class: "zm-dock", "aria-label": () => t("mobile.dock_label") },

    // ── LEFT of the orb: the menu, the conversation, and the wake word ──
    // 2026-10-24 (operator): the dashboards button is gone — «I do not know what it is». The deck already has its own
    // navigation, the PIPS above this bar (one per open card, the current one lit) and the side swipe; closing the
    // chat or a sheet is what shows the cards. Its slot went to the WAKE WORD, which the phone did not have.
    h("div", { class: "zm-side" },
      h("button", {
        class: () => cls(store.mobileMenuOpen()),
        "aria-label": () => t("mobile.menu"),
        onClick: () => { const v = !store.mobileMenuOpen(); store.setMobileMenuOpen(v); api.uiEvent("mobile:menu", { state: v ? "open" : "close" }); },
      }, raw(MENU)),

      h("button", {
        class: () => cls(store.chatOpen()),
        "aria-label": () => t("camera.chat_title"),
        onClick: () => { const v = !store.chatOpen(); store.setChatOpen(v); api.uiEvent("mobile:chat", { state: v ? "open" : "close" }); },
      }, raw(CHAT)),

      h("button", {
        class: () => cls(wakeOn()),
        "aria-label": () => (wakeOn() ? t("orb.wake_on", { name: store.assistantName() }) : t("orb.wake_off", { name: store.assistantName() })),
        onClick: toggleWake,
      }, raw(BOT)),
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
        class: () => "zm-ic zm-pwr pwr-off off" + (store.screenState() === "off" ? "" : " zm-hide"),
        "aria-label": () => t("orb.power_off"),
        onClick: () => power.centreTap("dock"),
      }, raw(PWR)),
      h("button", {
        // The orb itself. `aria-label` says what a tap DOES, not what the orb is — the state is already
        // announced by OrbMini's own label, and a screen-reader user needs to know this is the stop button.
        // `zm-blocked` is V2-573: the browser is refusing to play audio, so the operator hears nothing while
        // everything else looks healthy. It rides the ORB because that is where someone who cannot hear the
        // agent looks, and tapping it (a gesture) is exactly what the unlock needs.
        class: () => "zm-orb-btn pwr-" + store.agentState() + " st-" + store.screenState()
          + (store.screenState() === "off" ? " zm-hide" : "")
          + (store.audioBlocked() ? " zm-blocked" : ""),
        // What a tap DOES on this screen: bring the voice here, or stop the agent (V2-792 §9).
        "aria-label": () => (store.screenState() === "secondary" ? t("orb.centre_secondary") : t("mobile.orb_stop")),
        onClick: () => power.centreTap("dock"),
      }, ORB),
    ),

    // ── RIGHT of the orb: the microphone (privacy, one tap) and everything else ──
    h("div", { class: "zm-side" },
      h("button", {
        class: () => cls(store.agentLive() && !store.micMuted()),
        // `data-ctl="mic"` is what the CAPTURE GLOW is scoped to, the same marker the desktop orb bar uses.
        // Without it the glow rule could only key off `.zm-ic.on`, which is ALSO the chat and dashboards
        // buttons — three buttons carrying a filter meant for one (2026-09-20 review).
        "data-ctl": "mic",
        // The icon IS the level meter (2026-08-10, same request that put the VU on the desktop mic): it scales with
        // the REAL mic RMS through a CSS custom property, so it costs no re-render. With the mic muted or the agent
        // stopped there is no effect, because there is no level — the meter can only move when we are truly hearing.
        style: { "--vu": () => (store.agentLive() && !store.micMuted() ? String(Math.min(1, store.micLevel() * 6)) : "0") },
        "aria-label": () => (store.micMuted() ? t("camera.mic_unmute") : t("camera.mic_mute")),
        // Opening the mic by hand brings the voice to this surface (session.openMicHere); closing it is local.
        onClick: () => {
          if (store.micMuted() && session.openMicHere) session.openMicHere("dock");
          else mic.toggle("dock");
          api.uiEvent("mobile:mic", { state: store.micMuted() ? "muted" : "unmuted" });
        },
      }, () => raw(store.micMuted() ? MIC_OFF : MIC_ON)),

      // THE SPEAKER, back in the dock (operator, 2026-10-24). Opening it by hand brings the voice here, like the mic.
      h("button", {
        // Lilac only while the agent's voice really comes out of THIS screen (V2-792 §9): with the agent stopped or
        // the voice on another screen nothing is said here, whatever the toggle underneath says.
        class: () => cls(store.agentLive() && !store.botMuted()),
        "aria-label": () => (store.botMuted() ? t("orb.speaker_muted") : t("orb.speaker_unmuted")),
        onClick: () => {
          if (store.botMuted() && session.openSpeakerHere) session.openSpeakerHere("dock");
          else session.toggleBotMute();
          api.uiEvent("mobile:speaker", { state: store.botMuted() ? "muted" : "unmuted" });
        },
      }, () => raw(store.botMuted() ? SPK_OFF : SPK_ON)),

      // FEEDBACK (operator, 2026-10-24): right of everything. Since 2026-10-25 it opens its OWN sheet
      // (FeedbackSheet.js): it has a button of its own, so the menu no longer carries a second copy of it.
      h("button", {
        class: () => cls(store.mobileFeedbackOpen()),
        "aria-label": () => t("feedback.title"),
        onClick: () => {
          const v = !store.mobileFeedbackOpen();
          store.setMobileFeedbackOpen(v);
          api.uiEvent("mobile:feedback", { state: v ? "open" : "close" });
        },
      }, raw(FB)),
    ),
  );
}
