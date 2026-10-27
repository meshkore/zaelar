// ============================================================================
// AppsPane.js — the apps launcher on the phone, inside the ☰ menu (V2-823). Operator's decision (2026-10-27):
// «En el móvil, el lanzador de aplicaciones va dentro del menú ☰.»
//
// SAME LAUNCHER, PHONE CHROME. Everything an app's page says, the list it comes from and the way an app is opened
// are `app/components/apps-catalog.js` — the module the desk's apps window is built on — so the two shells cannot
// disagree about what an app's page declares (CRIT-K39). What this file adds is only what a phone does differently:
//   · ONE screen at a time: the list (System · Custom), then the tapped app's page, with ‹ back to the list. A
//     window's two columns do not fit 375px, and a page squeezed beside a list would truncate both.
//   · A TAP selects and shows the page — there is no double click on a touch screen (CRIT-K31: one tap opens what a
//     double click opens; here the page's «Open» is that one tap, because the tap on the row is spent on the page).
//   · «Open» hands the app to the deck through `hb:open-card` (the Deck listens on it like the desktop host) and
//     closes the menu, so he lands on the app.
// Every control respects the shell's 44px touch floor (mobile/app/styles.css, `.zm-apps`).
// ============================================================================

import { h, raw } from "../../../app/core/dom.js?v=2";
import { createEffect } from "../../../app/core/reactive.js?v=2";
import * as store from "../../../app/core/store.js?v=2";
import { t } from "../../../app/core/i18n.js?v=1";
import { appsCatalog } from "../../../app/components/apps-catalog.js?v=1";

const BACK = `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 6l-6 6 6 6"/></svg>`;

// `active` — a signal accessor: true while the menu shows this pane. `onBack` returns the menu to its rows.
export function AppsPane({ active, onBack }) {
  const cat = appsCatalog({ onOpened: () => store.setMobileMenuOpen(false) });

  // Each time the pane comes up, the list is read afresh (an app generated a minute ago belongs on it) and the
  // first screen is the list, never the page he looked at last time.
  let was = false;
  createEffect(() => {
    const on = !!active();
    if (on && !was) cat.load({ pick: false });
    if (!on && was) cat.clear();
    was = on;
  });

  const row = (w) => h("button", { class: "aw-row", "data-app": w.id, onClick: () => cat.select(w.id) },
    ...cat.rowFace(w));

  const back = () => (cat.sel() ? cat.clear() : onBack());

  return h("div", { class: () => "zm-apps" + (active() ? "" : " is-off"), "data-view": () => (cat.sel() ? "page" : "list") },
    h("div", { class: "zm-apps-h" },
      h("button", { class: "hb-iconbtn zm-apps-back", "aria-label": () => t("mobile.back"), onClick: back }, raw(BACK)),
      h("b", { class: "zm-apps-t" }, () => t("mobile.apps"))),
    h("div", { class: "zm-apps-list", role: "list" }, () => (cat.sel() ? null : cat.listBody(row))),
    h("article", { class: "zm-apps-page" }, () => cat.pageBody()));
}
