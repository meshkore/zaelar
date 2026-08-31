// ============================================================================
// DockBar.js — EVERY control, at the very bottom, ARRANGED AROUND THE ORB.  The mobile counterpart of the desktop's
// «eye» (Orb.js: an arc of 7 icons above the orb) and of the TopBar.  Operator's brief: «the orb and all options
// must be at the very bottom», refined 2026-08-18 to «an orb also in the centre of the footer… and then on the
// orb's sides, the rest of the buttons».
//
// WHY BOTTOM, AND WHY THAT MATTERS FOR LAYOUT: a phone is held in one hand and the thumb reaches the bottom third.
// So this bar is the ONLY chrome with a fixed position in this shell, and its height (--dock-h) is the ONE piece of
// geometry the rest of the shell knows about: every card ends `--dock-h` above the bottom edge so the bar can never
// cover the last line of a widget. On iOS it also pads itself with env(safe-area-inset-bottom), or it would sit
// under the home indicator and every tap would be a swipe-up instead.
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
// SIX CONTROLS, three per side, each through the SAME seam as its desktop twin — never a parallel path:
//   🎤 mic   → session.toggleMic() + store.micMuted()        (identical to Orb.js's mic slot, VU meter included)
//   🔊 spk   → session.toggleBotMute()                       (the ONE owner of silence, V2-087/V2-088)
//   📝 cap   → store.toggleCaptions()                        (same signal the CaptionBand and the desktop 📝 read)
//   ◉  orb   → the switch (above)
//   💬 chat  → store.chatOpen                               (the same signal the desktop chat panel reads)
//   ☰ menu   → store.mobileMenuOpen                         (mobile-only: account · profile · feedback · settings)
//
// THE GLYPHS ARE THE DESKTOP'S, BYTE FOR BYTE (operator: «as similar as possible to those already in the frontend of the
// UI»): MIC/SPK_ON/SPK_OFF/CAP/CHAT/PWR are copied from `app/components/Orb.js` so an operator who knows one shell
// reads the other without learning a second vocabulary. The ONE addition is MIC_OFF — the desktop only greys a
// muted mic, which is legible next to six other icons on a big screen and ambiguous as a lone icon on a phone, so
// the slash is drawn over the SAME base glyph rather than swapping in a different mic.
// ============================================================================

import { h, raw } from "../../../app/core/dom.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import * as session from "../../../app/services/session.js?v=3";
import * as api from "../../../app/services/api.js?v=2";
import { t } from "../../../app/core/i18n.js?v=1";
import { OrbMini } from "./OrbMini.js?v=2";

const SW = `viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"`;
const MIC_ON  = `<svg ${SW}><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/></svg>`;
const MIC_OFF = `<svg ${SW}><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/><path d="M4 4l16 16"/></svg>`;
const SPK_ON  = `<svg ${SW}><path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M18.5 5.5a9 9 0 0 1 0 13"/></svg>`;
const SPK_OFF = `<svg ${SW}><path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="m22 9-6 6"/><path d="m16 9 6 6"/></svg>`;
const CAP     = `<svg ${SW}><rect x="3" y="5" width="18" height="14" rx="3"/><path d="M7 10h5"/><path d="M7 14h9"/></svg>`;
const CHAT    = `<svg ${SW}><path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.4 9.06 9.06 0 0 1-4-.9L3 21l1.9-4.5a8.38 8.38 0 0 1-.9-4A8.5 8.5 0 0 1 12.5 4 8.38 8.38 0 0 1 21 11.5z"/></svg>`;
const MENU    = `<svg ${SW}><path d="M4 7h16"/><path d="M4 12h16"/><path d="M4 17h16"/></svg>`;
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
  api.uiEvent("mobile:power", { state: off ? "off" : "on" });
}

export function DockBar() {
  // Built ONCE, outside the reactive tree, because the visualiser holds this canvas by reference.
  const ORB = OrbMini();
  return h("nav", { class: "zm-dock", "aria-label": "zaelar controls" },

    // ── LEFT of the orb: the VOICE trio (what zaelar hears, what it says, and reading it instead of hearing it) ──
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
        class: () => cls(!store.botMuted()),
        "aria-label": () => (store.botMuted() ? t("orb.speaker_muted") : t("orb.speaker_unmuted")),
        onClick: () => { session.toggleBotMute(); api.uiEvent("mobile:speaker", { state: store.botMuted() ? "muted" : "unmuted" }); },
      }, () => raw(store.botMuted() ? SPK_OFF : SPK_ON)),

      h("button", {
        class: () => cls(store.captionsOn()),
        "aria-label": () => t("orb.captions_show"),
        onClick: () => { const v = store.toggleCaptions(); api.uiEvent("mobile:captions", { state: v ? "on" : "off" }); },
      }, raw(CAP)),
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
        class: () => "zm-orb-btn pwr-" + store.agentState() + (store.agentState() === "off" ? " zm-hide" : ""),
        "aria-label": () => t("mobile.orb_stop"),
        onClick: togglePower,
      }, ORB),
    ),

    // ── RIGHT of the orb: the two SURFACES (the conversation, and everything else) ──
    h("div", { class: "zm-side" },
      h("button", {
        class: () => cls(store.chatOpen()),
        "aria-label": () => t("camera.chat_title"),
        onClick: () => { const v = !store.chatOpen(); store.setChatOpen(v); api.uiEvent("mobile:chat", { state: v ? "open" : "close" }); },
      }, raw(CHAT)),

      h("button", {
        class: () => cls(store.mobileMenuOpen()),
        "aria-label": () => t("mobile.menu"),
        onClick: () => { const v = !store.mobileMenuOpen(); store.setMobileMenuOpen(v); api.uiEvent("mobile:menu", { state: v ? "open" : "close" }); },
      }, raw(MENU)),
    ),
  );
}
