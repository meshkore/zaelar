// apps-catalog.js — THE APPS LAUNCHER'S ONE SOURCE (V2-823): its data, its rows and the app's page, for both shells.
//
// The launcher lives in two places on purpose: the desk's apps WINDOW (AppsWindow.js, opened from the rail's corner)
// and, on the phone, the ☰ menu's «Apps» entry (mobile/app/shell/AppsPane.js — the operator's decision, 2026-10-27:
// «en el móvil, el lanzador de aplicaciones va dentro del menú ☰»). What differs between them is the CHROME and the
// GESTURE — a window with a list beside the page and a double click on a desk; one list, then one page, and a tap on
// a phone. What must NOT differ is what an app's page says, so the page is built here and only here: a second copy
// of `pageBody` is exactly how the phone would one day show an owner the desk does not, or the other way round.
//
// WHAT THIS MODULE OWNS
//   · the data — the list is `/widgets/registry` (user-surface rows only: a native surface is not an app); the page
//     is `/widgets/<id>/about` (`widgets/about.py`), cached per opening because it reads live connector state;
//   · the row's face (icon + name) and the System · Custom grouping — the row ELEMENT, with its gesture, is the
//     caller's, because the gesture is the one thing the two shells legitimately do differently;
//   · the page — ONLY the keys the server sent, each block tagged `data-field`. There is no placeholder for a missing
//     owner or date, by design (CRIT-K39);
//   · opening — `hb:open-card`, the door every opener uses; both hosts (desktop.js and the phone's Deck.js) listen
//     on it. This module holds no second way of opening an app.
//
// Layout-neutral: the classes below (`aw-row`, `aw-pagehead`, `aw-facts`…) are styled in core/shared-surfaces.css,
// which both shells link; where the page SITS (a column of a window, a menu sheet) is each shell's own CSS.
import { h, raw } from "../core/dom.js?v=2";
import { createSignal } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as api from "../services/api.js?v=2";
import { t } from "../core/i18n.js?v=1";
import { APPS_ICON } from "../lib/icons.js?v=1";

// A key the bundle does not carry comes back from t() as the key itself (truthy) — here that means «no label for
// this id», and the id is the honest thing to show.
const tOr = (key, fallback) => { const s = t(key); return s === key ? fallback : s; };

export function fmtDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ""));
  if (!m) return String(iso || "");
  try {
    return new Intl.DateTimeFormat(store.lang() || "en", { dateStyle: "long", timeZone: "UTC" })
      .format(new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])));
  } catch (_) { return iso; }
}

// `onOpened(id)` runs after the app was handed to the host — the caller closes its own chrome there (the window, the
// menu sheet). The open itself is not the caller's to do.
export function appsCatalog({ onOpened = () => {} } = {}) {
  const [rows, setRows] = createSignal([]);
  const [loaded, setLoaded] = createSignal(false);
  const [sel, setSel] = createSignal(null);
  const [page, setPage] = createSignal(null);
  const pages = new Map();            // id → page, for this opening only (the page reads live connector state)

  const open = (id) => {
    if (!id) return;
    try { document.dispatchEvent(new CustomEvent("hb:open-card", { detail: { id, by: "hand" } })); } catch (_) {}
    onOpened(id);
  };

  const select = async (id) => {
    setSel(id);
    if (pages.has(id)) { setPage(pages.get(id)); return; }
    setPage(null);
    let p = null;
    try {
      const r = await fetch("/widgets/" + encodeURIComponent(id) + "/about", { cache: "no-store" });
      if (r.ok) p = await r.json();
    } catch (_) {}
    if (p && p.id) pages.set(id, p);
    if (sel() === id) setPage(p && p.id ? p : { id, missing: true });
  };

  const clear = () => { setSel(null); setPage(null); };

  // `pick`: select an app as soon as the list is in (the window keeps the previous one, else the first system app).
  // The phone passes false — its first screen is the list, and a page appears only when he taps one.
  const load = async ({ pick = false } = {}) => {
    setLoaded(false); pages.clear();
    const r = await api.getWidgetsRegistry();
    const byName = (a, b) => String(a.name || a.id).localeCompare(String(b.name || b.id));
    const list = ((r && r.registry) || []).filter(w => w && w.surface === "user" && w.id).sort(byName);
    setRows(list); setLoaded(true);
    if (!pick) { clear(); return list; }
    const keep = list.find(w => w.id === sel());
    const first = keep || list.find(w => w.origin === "builtin") || list[0];
    if (first) select(first.id); else clear();
    return list;
  };

  // ── the list. `row(w)` builds one row element (the caller's gesture); `rowFace(w)` is what every row shows.
  const rowFace = (w) => [h("span", { class: "aw-icon" }, raw(APPS_ICON)), h("span", { class: "aw-name" }, w.name || w.id)];

  const listBody = (row) => {
    if (!loaded()) return [h("div", { class: "hb-empty-state" }, () => t("appsWin.loading"))];
    const all = rows();
    if (!all.length) return [h("div", { class: "hb-empty-state" }, () => t("appsWin.empty"))];
    const sys = all.filter(w => w.origin === "builtin"), mine = all.filter(w => w.origin !== "builtin");
    const out = [];
    if (sys.length) out.push(h("div", { class: "hb-sectitle aw-group" }, () => t("chat.appsSystem")), ...sys.map(row));
    if (mine.length) out.push(h("div", { class: "hb-sectitle aw-group" }, () => t("chat.appsCustom")), ...mine.map(row));
    return out;
  };

  // ── the page: ONLY the keys the server sent. Each block carries `data-field` so a reader (and the tests) can tell
  // what the page claims about this app.
  const fact = (field, label, value) =>
    h("div", { class: "aw-fact", "data-field": field },
      h("dt", { class: "aw-factk" }, label), h("dd", { class: "aw-factv" }, value));

  const pageBody = () => {
    const p = page();
    if (!sel()) return [];
    if (!p) return [h("div", { class: "hb-empty-state" }, () => t("appsWin.loading"))];
    const facts = [];
    if (p.owner) facts.push(fact("owner", t("appsWin.owner"), p.owner));
    if (p.created) facts.push(fact("created", t("appsWin.created"), fmtDate(p.created)));
    if (p.licence) facts.push(fact("licence", t("appsWin.licence"), tOr("apps.licence." + p.licence, p.licence)));
    const name = p.name || (rows().find(w => w.id === p.id) || {}).name || p.id;
    const out = [
      h("div", { class: "aw-pagehead" },
        h("span", { class: "aw-bigicon" }, raw(APPS_ICON)),
        h("div", { class: "aw-titles" },
          h("h2", { class: "aw-title" }, name),
          p.origin && p.origin !== "builtin"
            ? h("span", { class: "hb-badge hb-badge--accent hb-badge--bare", "data-field": "custom" }, t("chat.appsCustom")) : null),
        h("button", { class: "hb-btn hb-btn--primary aw-open", onClick: () => open(p.id) }, t("appsWin.open"))),
    ];
    if (p.forked) out.push(h("p", { class: "hb-panel-note aw-forked", "data-field": "forked" },
                             t("appsWin.forked", { date: fmtDate(p.forked) })));
    if (facts.length) out.push(h("dl", { class: "aw-facts" }, ...facts));
    if (p.about) out.push(h("section", { class: "aw-sec", "data-field": "about" },
                            h("div", { class: "hb-sectitle" }, t("appsWin.about")),
                            h("p", { class: "aw-about" }, p.about)));
    if (Array.isArray(p.connectors)) out.push(h("section", { class: "aw-sec", "data-field": "connectors" },
      h("div", { class: "hb-sectitle" }, t("appsWin.connectors")),
      p.connectors.length
        ? h("ul", { class: "aw-conns" }, ...p.connectors.map(c =>
            h("li", { class: "aw-conn", "data-conn": c.id },
              h("span", { class: "aw-connn" }, c.label || c.id),
              h("span", { class: "hb-badge " + (c.connected ? "hb-badge--ok" : "") },
                c.connected ? t("appsWin.connected") : t("appsWin.notConnected")))))
        : h("p", { class: "hb-hint" }, t("appsWin.noConnectors"))));
    return out;
  };

  return { rows, loaded, sel, page, load, select, clear, open, rowFace, listBody, pageBody };
}
