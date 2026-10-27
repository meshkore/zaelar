// AppsWindow — the apps launcher opened from the rail's corner (V2-823).
//
// The operator's request (2026-10-27): beside the desk's own tools in the bottom-right corner, an «apps» icon
// that opens a WINDOW over the desk — the desk is not emptied — with the apps on the left (icon + name, a finite
// list) and, on the right, the selected app's page: who owns it, when it was created, its licence, what it does,
// the connectors it can use, and an «Open» button. ONE click selects and shows the page; a DOUBLE click opens the
// app and closes the window. The wall's «Apps» tab stays as the direct shortcut (one click opens) — both on purpose.
//
// WHERE THE DATA AND THE PAGE COME FROM: `apps-catalog.js`, the launcher's one source — the list
// (`/widgets/registry`), the page (`/widgets/<id>/about`, painting ONLY what arrives) and the open (`hb:open-card`).
// The phone's ☰ «Apps» entry builds on the same module; this file is the WINDOW: its chrome, the double click and the
// arrow keys — the parts a desk has and a phone does not.
//
// Not voice-addressable in v1 (`name: null` in SYSTEM_SURFACES): the voice already reaches the catalogue through the
// wall's Apps tab, and a second surface answering to «apps» would be a near-miss of that one.
import { h, raw } from "../core/dom.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import { t } from "../core/i18n.js?v=1";
import { APPS_ICON, CLOSE_ICON } from "../lib/icons.js?v=1";
import { appsCatalog } from "./apps-catalog.js?v=1";

export function AppsWindow() {
  const close = () => store.setAppsWindowOpen(false);
  const cat = appsCatalog({ onOpened: close });
  const { sel, select } = cat;
  let listEl;

  const load = async () => {
    await cat.load({ pick: true });
    setTimeout(() => { const b = listEl && listEl.querySelector(".aw-row.is-selected"); if (b) b.focus(); }, 0);
  };

  // ── the list: rows are built once per load and only their CLASS follows the selection. Rebuilding a row between
  // the two clicks of a double click would swap the node under the pointer and the dblclick would never fire.
  const row = (w) => h("button", {
      class: () => "aw-row" + (sel() === w.id ? " is-selected" : ""), "data-app": w.id, role: "option",
      "aria-selected": () => (sel() === w.id ? "true" : "false"), title: () => t("appsWin.hint"),
      onClick: () => select(w.id),
      onDblClick: () => cat.open(w.id),
      onKeyDown: (e) => { if (e.key === "Enter") { e.preventDefault(); cat.open(w.id); } },
    }, ...cat.rowFace(w));

  const onListKey = (e) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const btns = [...listEl.querySelectorAll(".aw-row")];
    const i = btns.findIndex(b => b.dataset.app === sel());
    const next = btns[Math.max(0, Math.min(btns.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))];
    if (next) { e.preventDefault(); next.focus(); select(next.dataset.app); }
  };

  const onKey = (e) => { if (e.key === "Escape" && store.appsWindowOpen()) close(); };
  window.addEventListener("keydown", onKey);

  const el = h("div", { class: () => "appswin" + (store.appsWindowOpen() ? " open" : ""), id: "appswin",
                        onClick: (e) => { if (e.target === el) close(); } },
    h("section", { class: "aw-shell", role: "dialog", "aria-modal": "true", "aria-label": () => t("appsWin.title") },
      h("header", { class: "hb-toolbar aw-head" },
        h("span", { class: "aw-headicon" }, raw(APPS_ICON)),
        h("span", { class: "hb-toolbar-title" }, () => t("appsWin.title")),
        h("span", { class: "hb-toolbar-spacer" }),
        h("span", { class: "hb-toolbar-sub aw-hint" }, () => t("appsWin.hint")),
        h("button", { class: "hb-iconbtn hb-iconbtn--lg aw-x", "aria-label": () => t("appsWin.close"),
                      title: () => t("appsWin.close"), onClick: close }, raw(CLOSE_ICON))),
      h("div", { class: "aw-body" },
        h("nav", { class: "aw-list", role: "listbox", "aria-label": () => t("appsWin.list"),
                   ref: (n) => (listEl = n), onKeyDown: onListKey }, () => cat.listBody(row)),
        h("article", { class: "aw-page" }, () => cat.pageBody()))));

  let wasOpen = false;
  createEffect(() => { const o = store.appsWindowOpen(); if (o && !wasOpen) load(); wasOpen = o; });
  return el;
}
