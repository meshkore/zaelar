// ============================================================================
// VoiceHeldNotice.js — the voice lock, made VISIBLE.
//
// THE FACT: server/livekit_api.py allows exactly ONE live voice session per machine (heartbeat every ~4 s, 12 s
// TTL). Two open mics against the same agent drive the pipeline mad — two agents, two mics, a doubled event
// stream — so whoever asks second gets `{ok:false, held:true}` and nothing else.
//
// THE CONSEQUENCE THIS SHELL CREATED: until now the two surfaces that could hold that lock were two tabs on the
// same computer, so "close the other one" was advice the operator could act on in one second. A phone and a laptop
// are not two tabs. The brief for this whole initiative assumed «dos frontends se conectan al mismo server, y ya
// está» — almost. The voice is the one thing that cannot be in two places.
//
// THE ANSWER: do not fight, do not retry in a loop, and above all do not paint the phone as live while it holds no
// lock. Say where the voice is, and offer to bring it here — one tap. The surface that loses it drops to chat +
// observer, which already works (chat and voice have been independent since V2-088, and SSE has come up without
// voice since 2026-08-09). Nothing dies; a microphone moves.
//
// This is the «visible state, not silent state» rule applied to the one piece of state that this shell newly makes
// ambiguous: a state that can mislead has to be SEEN and fixable in one gesture.
// ============================================================================

import { h } from "../../../app/core/dom.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import * as session from "../../../app/services/session.js?v=3";
import * as api from "../../../app/services/api.js?v=2";
import { t } from "../../../app/core/i18n.js?v=1";

export function VoiceHeldNotice() {
  const take = async () => {
    api.uiEvent("mobile:voice_takeover", {});
    // Claim the lock for THIS surface, then connect. The loser needs nothing new: its heartbeat (~4 s) will answer
    // ok:false, and session-lk.js already reacts to that by stopping and saying so on its own screen. So the
    // handover costs one heartbeat interval and no new machinery.
    const sid = typeof session.sessionId === "function" ? session.sessionId() : null;
    if (!sid) return;                                   // no lock identity (non-LiveKit engine) → nothing to steal
    const r = await api.sessionSteal(sid);
    if (!r || r.ok === false) return;                   // the notice stays up: failing quietly would be a lie
    store.setMobileVoiceHeld(false);
    store.setMicBlocked({ show: false, msg: "" });      // clear the desktop-shaped 🚫 flag we mirrored from
    try { await session.start(); } catch (_) { /* the shared retry loop takes it from here */ }
  };

  return h("div", {
    class: () => "zm-held" + (store.mobileVoiceHeld() ? " show" : ""),
    role: "status",
  },
    h("p", null, () => t("mobile.voice_held")),
    h("div", null,
      h("button", { class: "zm-primary", onClick: take }, () => t("mobile.voice_take")),
      h("button", {
        class: "zm-ghost",
        // Dismiss ≠ resolved. Staying in text is a legitimate choice, and it must not silently re-arm the mic:
        // the auto-connect in main.js checks this flag, so dismissing means "I will use text", not "try again".
        onClick: () => { store.setMobileVoiceHeld(false); store.setChatOpen(true); },
      }, () => t("mobile.voice_text")),
    ),
  );
}
