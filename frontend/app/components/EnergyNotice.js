// EnergyNotice — the agent stopped because the account ran out of Energy, SAID ON SCREEN, with the way out (V2-785).
//
// Until 2026-10-22 running out was only ever SPOKEN: the voice said «You're out of Energy…», the session ended, and
// the screen showed nothing — no notice, no link — so the person who heard it had nowhere to go. The engine now
// records the state where every road to "out of energy" passes (`nucleo/energy/limits.request_close`) and sends it
// on the `energy` event the battery already listens to, and in `/api/energy` for a page opened afterwards. This
// renders it: what happened, and one button to the configured account page.
//
// SHARED by both shells (desktop `system-surfaces.js`, phone `mobile-surfaces.js`); its CSS lives in
// `core/shared-surfaces.css`. Every word is an i18n key. Closable, unlike the model fault: the agent is stopped
// either way, and the person may want to read what is on screen while they go to the account page.
import { h } from "../core/dom.js?v=2";
import * as store from "../core/store.js?v=2";
import { t } from "../core/i18n.js?v=1";
import * as api from "../services/api.js?v=2";
import { accountLink, noticeReason, noticeKind } from "../core/account-link.js?v=2";

// TWO notices, chosen by WHAT HAPPENED (V2-801): "out" — the account has no Energy (the engine was told so) — with
// the Top up link; "paused" — the agent stopped without knowing the account's state (its lease could not be
// renewed) — which never claims the account is empty and never pushes a top-up. `noticeKind` also refuses "out"
// while the battery shows Energy, so the notice and the battery cannot contradict each other.
export function EnergyNotice() {
  const reason = () => noticeReason(store.energy(), store.energyNoticeClosed());
  const kind = () => noticeKind(store.energy());
  const close = () => {
    api.uiEvent("energy:notice_close", { reason: reason(), kind: kind() });
    store.setEnergyNoticeClosed(reason());
  };
  return h("div", { class: () => "en-ovl" + (reason() ? " on" : "") + " " + kind() },
    h("div", { class: "en-box", role: "alertdialog", "aria-live": "assertive", "aria-labelledby": "en-title" },
      h("div", { class: "en-mark", "aria-hidden": "true" }, "⚡"),
      h("h3", { class: "en-title", id: "en-title" }, () => t(`energy.${kind()}.title`)),
      h("p", { class: "en-body" }, () => t(`energy.${kind()}.body`)),
      h("div", { class: "en-actions" },
        h("a", {
          class: "en-btn primary",
          href: () => accountLink(store.accountUrl(), "buy") || null,
          hidden: () => kind() !== "out",
          target: "_blank",
          rel: "noopener",
          onClick: () => api.uiEvent("energy:top_up", { reason: reason() }),
        }, () => t("energy.out.top_up")),
        h("button", { class: "en-btn", onClick: close }, () => t("energy.out.close")),
      ),
    ),
  );
}
