// ============================================================================
// MenuSheet.js — the ☰ sheet: the mobile home for everything the desktop keeps in its top bar and its floating
// launcher.  Operator's brief: «a menu button also to access feedback, the account, the profile, some
// other things… a small configuration device and from there manage all that too».
//
// WHAT IT HOLDS, and where each row's behaviour actually lives:
//   · Energy      — the balance, read from store.energy() (the SSE keeps it live; no polling here)
//   · Account     — cloud only (store.cloudProfile), because on self-host there is no account to open
//   · Feedback    — sends through services/feedback-api.js, the SAME two functions the desktop widget uses
//   · Settings    — opens SettingsSheet (the «small settings device»)
//   · Voice       — cycles the TTS voice (session.cycleVoice), the same seam as tapping the orb
//   · Shell       — "open the desktop version": sets zaelar_shell=desktop and leaves. THE ESCAPE HATCH, and it is
//                   not optional — a shell you cannot leave is a trap, and the shell picker in index.html would
//                   otherwise bounce a tablet user back here on every load.
//
// The feedback form is INLINE rather than a second sheet on purpose: the desktop learned (V2-100) that the whole
// value of this feature is that it takes one gesture. Two sheets deep and nobody reports anything.
// ============================================================================

import { h, raw } from "../../../app/core/dom.js?v=2";
import { createSignal } from "../../../app/core/reactive.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import * as session from "../../../app/services/session.js?v=3";
import * as api from "../../../app/services/api.js?v=2";
import { listFeedback, sendFeedback } from "../../../app/services/feedback-api.js?v=1";
import { sendOutcome, listOutcome, lineFor } from "../../../app/services/feedback-state.js?v=1";
import { t } from "../../../app/core/i18n.js?v=1";

const CHEV = `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9 6l6 6-6 6"/></svg>`;

// One menu row: bold label, quiet subtitle, chevron. `label`/`sub` may be a string OR a function — a function is a
// reactive binding (core/dom.js), which is how a row's subtitle can track a signal (the current voice, say) without
// this component knowing which signal it was.
function Row(label, sub, onClick) {
  return h("button", { class: "zm-row", onClick },
    h("span", { class: "zm-row-t" },
      h("b", null, label),
      sub ? h("small", null, sub) : null,
    ),
    raw(CHEV),
  );
}

export function MenuSheet() {
  const [fbOpen, setFbOpen] = createSignal(false);
  const [fbMsg, setFbMsg] = createSignal("");
  const [fbDone, setFbDone] = createSignal("");
  let fbInput = null;

  const close = () => store.setMobileMenuOpen(false);

  const doSend = async () => {
    const msg = (fbInput && fbInput.value || "").trim();
    if (!msg) return;
    store.setFeedbackSending(true);
    // includeSessionEvidence: true — on a phone the operator cannot copy a trace id or open the debug panel, so a
    // report without the evidence bundle is a report we cannot act on. The desktop makes this a checkbox; here it
    // is the default, and the row says so out loud rather than attaching it silently.
    const r = await sendFeedback({ message: msg, includeSessionEvidence: true });
    store.setFeedbackSending(false);
    // Same reading as the desktop panel, from the same module (V2-256). This surface HAD the failure
    // branch and the desktop did not — one rule in two places is how that happens, so now there is one.
    const out = sendOutcome(r);
    if (!out.ok) { setFbDone(lineFor(out, t)); return; }
    fbInput.value = "";
    setFbDone(t("feedback.sent"));
    listFeedback().then((d) => store.setFeedbackItems(listOutcome(d).items));
  };

  return h("section", {
    class: () => "zm-sheet zm-menu" + (store.mobileMenuOpen() ? " open" : ""),
    "aria-hidden": () => (store.mobileMenuOpen() ? "false" : "true"),
  },
    h("header", { class: "zm-sheet-h" },
      h("div", { class: "zm-sheet-grab" }),
      h("h2", null, "zaelar"),
      h("button", { class: "zm-sheet-x", "aria-label": () => t("desktop.close"), onClick: close }, "×"),
    ),

    h("div", { class: "zm-rows" },
      // ── ENERGY: the balance is the one number a paying user checks, so it is the first row and it shows the
      //    value inline instead of hiding it one tap deep. `known:false` (self-host, or the machine still booting)
      //    renders "—", never a fabricated 0 — a wrong balance is worse than no balance.
      h("div", { class: () => "zm-energy" + (store.energy().cloud ? "" : " hide") },
        h("span", null, () => t("energy.label")),
        h("b", null, () => {
          const e = store.energy();
          return e.known && e.balance != null ? String(Math.round(e.balance)) : "—";
        }),
        h("i", {
          style: {
            width: () => {
              const e = store.energy();
              if (!e.known || !e.capacity) return "0%";
              return Math.max(0, Math.min(100, (e.balance / e.capacity) * 100)) + "%";
            },
          },
        }),
      ),

      // ── ACCOUNT — cloud only. On self-host there is no account behind this, so the row is not rendered at all
      //    rather than rendered and dead: a control that does nothing teaches the operator to distrust the others.
      () => store.cloudProfile()
        ? Row(() => t("mobile.account"), () => t("mobile.account_sub"),
            () => { location.href = "/account"; })
        : null,

      Row(() => t("mobile.voice"), () => (store.voices()[store.voiceIdx()] || {}).label || "",
        () => { session.cycleVoice(); api.uiEvent("mobile:voice_cycle", {}); }),

      Row(() => t("mobile.settings"), () => t("mobile.settings_sub"),
        () => { store.setMobileSettingsOpen(true); }),

      // ── FEEDBACK, inline (one gesture, V2-100) ──
      h("button", { class: "zm-row", onClick: () => setFbOpen(!fbOpen()) },
        h("span", { class: "zm-row-t" },
          h("b", null, () => t("feedback.title")),
          h("small", null, () => t("mobile.feedback_sub")),
        ),
        raw(CHEV),
      ),
      h("div", { class: () => "zm-fb" + (fbOpen() ? " open" : "") },
        h("textarea", {
          ref: (el) => (fbInput = el), rows: "4",
          placeholder: () => t("feedback.placeholder"),
          onInput: (e) => setFbMsg(e.target.value),
        }),
        h("small", null, () => t("mobile.feedback_evidence")),
        h("button", {
          class: "zm-primary",
          disabled: () => store.feedbackSending() || !fbMsg().trim(),
          onClick: doSend,
        }, () => store.feedbackSending() ? (t("feedback.sending")) : (t("feedback.send"))),
        h("p", { class: "zm-fb-done" }, () => fbDone()),
      ),

      // ── THE ESCAPE HATCH. Persists the choice so index.html's picker stops redirecting this device.
      Row(() => t("mobile.desktop"), () => t("mobile.desktop_sub"),
        () => { try { localStorage.setItem("zaelar_shell", "desktop"); } catch (_) {} location.replace("/?desktop=1"); }),
    ),
  );
}
