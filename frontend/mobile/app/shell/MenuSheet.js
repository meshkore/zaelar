// ============================================================================
// MenuSheet.js — the ☰ sheet: the mobile home for everything the desktop keeps in its top bar and its floating
// launcher.  Operator's brief: «a menu button also to access feedback, the account, the profile, some
// other things… a small configuration device and from there manage all that too».
//
// WHAT IT HOLDS, and where each row's behaviour actually lives:
//   · Account     — cloud only (store.cloudProfile): plan, Energy, billing, renewal and sign-out live on the account
//                   page, so this row is the door to all of it. FIRST, because it is what a phone user comes here for.
//   · Energy      — the balance, read from store.energy() (the SSE keeps it live); tapping it opens the top-up
//   · Settings    — opens SettingsSheet (the «small settings device»)
//   · Feedback is NOT here any more (2026-10-25, operator): it has its own dock button and its own sheet
//     (FeedbackSheet.js); a second copy at the bottom of the menu read as clutter.
//   · Voice       — cycles the TTS voice (session.cycleVoice), the same seam as tapping the orb
//   · Shell       — "open the desktop version": sets zaelar_shell=desktop and leaves. THE ESCAPE HATCH, and it is
//                   not optional — a shell you cannot leave is a trap, and the shell picker in index.html would
//                   otherwise bounce a tablet user back here on every load.
//
// ============================================================================

import { h, raw } from "../../../app/core/dom.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import * as session from "../../../app/services/session.js?v=3";
import * as api from "../../../app/services/api.js?v=2";
import { t } from "../../../app/core/i18n.js?v=1";
import { accountLink } from "../../../app/core/account-link.js?v=1";
import * as daemon from "../../../app/services/daemon.js?v=3";
import { ProcessEntry } from "../../../app/components/ProcessEntry.js?v=1";

// The daemon poll runs here too: the desktop starts it from the setup surface, which this shell does not
// mount. Without this the row would always read "not connected", which is a wrong answer rather than a
// missing one — the worst of the three states a status row can be in.
daemon.start();

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
  const openAccount = (section) => {
    // V2-785: the engine's account url, never a relative "/account" — in a hosted deployment that is this agent's
    // own origin, where no account page exists.
    const u = accountLink(store.accountUrl(), section);
    if (u) window.open(u, "_blank", "noopener");
  };
  const close = () => store.setMobileMenuOpen(false);

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
      // ── RUNNING PROCESSES (V2-822). The phone has no processes tab, and since the cards stopped telling their
      //    errand's progress (a card shows only its deliverable), this is where a running process is told: the
      //    same entry the desktop's processes tab draws, from the same record. Absent when nothing runs.
      h("div", { class: "zm-procs" }, () => {
        const live = store.liveProcesses();      // the same reading as the dock's count (V2-822)
        if (!live.length) return null;
        return [h("div", { class: "zm-procs-t" }, () => t("chat.procMobileTitle")),
                ...live.map(x => h("div", { class: "zm-proc" },
                  h("b", null, (x.title || x.note || "").trim() || t("chat.working")),
                  ProcessEntry(x.id)))];
      }),

      // ── ACCOUNT — cloud only. On self-host there is no account behind this, so the row is not rendered at all
      //    rather than rendered and dead: a control that does nothing teaches the operator to distrust the others.
      () => store.cloudProfile()
        ? Row(() => t("mobile.account"), () => t("mobile.account_sub"), () => openAccount())
        : null,

      // ── ENERGY: the balance shows inline instead of hiding it one tap deep, and the row IS the top-up (the
      //    account page's #buy, like the desktop battery). `known:false` (the machine still booting) renders "—",
      //    never a fabricated 0 — a wrong balance is worse than no balance.
      h("button", { class: () => "zm-energy" + (store.energy().cloud ? "" : " hide"), onClick: () => openAccount("buy") },
        h("span", null, () => t("energy.label")),
        h("b", null, () => {
          const e = store.energy();
          return e.known && e.balance != null ? String(Math.round(e.balance)) : "—";
        }),
        // The TRACK is the cycle's Energy and the fill is what is left. The fill used to be the flex item itself,
        // and `flex: 1 1 auto` stretched it over its own width: 61 of 400 drew a full bar.
        h("span", { class: "zm-energy-track" }, h("i", {
          style: {
            width: () => {
              const e = store.energy();
              if (!e.known || !e.capacity) return "0%";
              return Math.max(0, Math.min(100, (e.balance / e.capacity) * 100)) + "%";
            },
          },
        })),
      ),

      Row(() => t("mobile.settings"), () => t("mobile.settings_sub"),
        () => { store.setMobileSettingsOpen(true); }),

      Row(() => t("mobile.voice"), () => (store.voices()[store.voiceIdx()] || {}).label || "",
        () => { session.cycleVoice(); api.uiEvent("mobile:voice_cycle", {}); }),

      // ── 🖥 THE LOCAL DAEMON, READ ONLY (V2-575 P1). A phone does not install a desktop daemon, so this row
      //    has no chevron and no click: it REPORTS. It is here because "is my computer connected?" is a
      //    question somebody asks from wherever they are, and a mobile shell that simply omitted the answer
      //    would read as "this device has no daemon" rather than "you cannot set it up from here".
      h("div", { class: () => "zm-row zm-row-static" + (daemon.isOffered() ? "" : " is-off") },
        h("span", { class: "zm-row-t" },
          h("b", null, () => t("daemon.mobile.row")),
          h("small", null, () => (daemon.isConnected() ? t("daemon.ok.lead") : t("daemon.mobile.hint"))),
        ),
      ),

      // ── THE ESCAPE HATCH. Persists the choice so index.html's picker stops redirecting this device.
      Row(() => t("mobile.desktop"), () => t("mobile.desktop_sub"),
        () => { try { localStorage.setItem("zaelar_shell", "desktop"); } catch (_) {} location.replace("/?desktop=1"); }),
    ),
  );
}
