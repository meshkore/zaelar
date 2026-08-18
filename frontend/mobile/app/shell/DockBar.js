// ============================================================================
// DockBar.js — EVERY control, at the very bottom.  The mobile counterpart of the desktop's «eye» (Orb.js: an arc
// of 7 icons above the orb) and of the TopBar.  Operator's brief: «el orbe y todas las opciones tendrán que estar
// abajo del todo».
//
// WHY BOTTOM, AND WHY THAT MATTERS FOR LAYOUT: a phone is held in one hand and the thumb reaches the bottom third.
// So this bar is the ONLY chrome with a fixed position in this shell, and its height (--dock-h) is the ONE piece of
// geometry the rest of the shell knows about: every card ends `--dock-h` above the bottom edge so the bar can never
// cover the last line of a widget. On iOS it also pads itself with env(safe-area-inset-bottom), or it would sit
// under the home indicator and every tap would be a swipe-up instead.
//
// FIVE CONTROLS, and each one goes through the SAME seam as its desktop twin — never a parallel path:
//   ◉ orb   → OrbMini (tap = cycle voice, like the desktop orb)
//   🎤 mic  → session.toggleMic() + store.micMuted()          (identical to Orb.js's mic slot)
//   ⏻ power → store.powerOff + api.runStop()/runStart()       (the GLOBAL switch, V2-092 — server-side truth)
//   💬 chat → store.chatOpen                                  (the same signal the desktop chat panel reads)
//   ☰ menu  → store.mobileMenuOpen                            (mobile-only: account · profile · feedback · settings)
//
// That «same seam» rule is the whole reason this file is short. ⏻ in particular MUST keep going through
// api.runStop()/runStart(): the switch is the SERVER's state since V2-092, so a mobile-only power button that just
// flipped a local signal would show "stopped" on the phone while the agent kept working — the exact class of lying
// state the desktop already paid for once.
// ============================================================================

import { h, raw } from "../../../app/core/dom.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import * as session from "../../../app/services/session.js?v=3";
import * as api from "../../../app/services/api.js?v=2";
import { t } from "../../../app/core/i18n.js?v=1";
import { OrbMini } from "./OrbMini.js?v=1";

const MIC_ON = `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M12 3a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3z"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/></svg>`;
const MIC_OFF = `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M12 3a3 3 0 0 1 3 3v5"/><path d="M9 9v3a3 3 0 0 0 4.6 2.5"/><path d="M5 11a7 7 0 0 0 10.5 6"/><path d="M12 18v3"/><path d="M4 4l16 16"/></svg>`;
const PWR = `<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 3v9"/><path d="M18.4 6.6a9 9 0 1 1-12.8 0"/></svg>`;
const CHAT = `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-8 8H8l-5 3 1.5-4.5A8 8 0 1 1 21 12z"/></svg>`;
const MENU = `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7h16"/><path d="M4 12h16"/><path d="M4 17h16"/></svg>`;

// BLUE = on/live, pale GREY = off/closed. Same language as the desktop's lid icons, so an operator who knows one
// shell can read the other without learning a second vocabulary.
const cls = (on) => "zm-ic" + (on ? " on" : " off");

export function DockBar() {
  return h("nav", { class: "zm-dock", "aria-label": "zaelar controls" },
    OrbMini(),
    h("div", { class: "zm-ctl" },
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
        // The ONE icon that can never lie: it paints the four REAL states (store.agentState) — live · starting ·
        // off · stalled — not the persisted flag. `stalled` = "should be on and is not", which is the state whose
        // absence once had the operator talking to a dead agent.
        class: () => "zm-ic zm-pwr pwr-" + store.agentState() + (store.agentLive() ? " on" : " off"),
        "aria-label": () => t("orb.power_" + store.agentState()),
        onClick: () => {
          const off = !store.powerOff();
          // Stamp the command BEFORE applying it, so a server reconciliation that went to fetch the state before
          // this instant stays quiet. Without it, a cold start tears down the session just asked for (main.js).
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
        },
      }, raw(PWR)),

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
