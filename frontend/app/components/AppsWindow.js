// AppsWindow — the apps launcher opened from the rail's corner (V2-823).
//
// The operator's request (2026-10-27): beside the desk's own tools in the bottom-right corner, an «apps» icon
// that opens a WINDOW over the desk — the desk is not emptied — with the apps on the left (icon + name, a finite
// list) and, on the right, the selected app's page: who owns it, when it was created, its licence, what it does,
// the connectors it can use, and an «Open» button. ONE click selects and shows the page; a DOUBLE click opens the
// app and closes the window. The wall's «Apps» tab stays as the direct shortcut (one click opens) — both on purpose.
//
// WHERE THE DATA COMES FROM. Nothing new to keep in sync:
//   · the list is `/widgets/registry` — the very read the wall's Apps tab makes (user-surface rows only);
//   · the page is `/widgets/<id>/about` (`widgets/about.py`), a projection of the manifest plus the live connector
//     inventory read with the one `serves()` reader. A field the manifest does not declare does not arrive, and
//     this file paints ONLY what arrives — there is no placeholder for a missing owner or date, by design.
// WHERE A CLICK GOES. Opening is `hb:open-card`, the door every other opener uses; this window holds no second way.
//
// Not voice-addressable in v1 (`name: null` in SYSTEM_SURFACES): the voice already reaches the catalogue through the
// wall's Apps tab, and a second surface answering to «apps» would be a near-miss of that one.
import { h, raw } from "../core/dom.js?v=2";
import { createSignal, createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as api from "../services/api.js?v=2";
import { t } from "../core/i18n.js?v=1";
import { APPS_ICON, CLOSE_ICON } from "../lib/icons.js?v=1";

// A key the bundle does not carry comes back from t() as the key itself (truthy) — here that means «no label for
// this id», and the id is the honest thing to show.
const tOr = (key, fallback) => { const s = t(key); return s === key ? fallback : s; };

function fmtDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ""));
  if (!m) return String(iso || "");
  try {
    return new Intl.DateTimeFormat(store.lang() || "en", { dateStyle: "long", timeZone: "UTC" })
      .format(new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])));
  } catch (_) { return iso; }
}

export function AppsWindow() {
  const [rows, setRows] = createSignal([]);
  const [loaded, setLoaded] = createSignal(false);
  const [sel, setSel] = createSignal(null);
  const [page, setPage] = createSignal(null);
  const pages = new Map();            // id → page, for this opening only (the page reads live connector state)
  let listEl;

  const close = () => store.setAppsWindowOpen(false);
  const openApp = (id) => {
    if (!id) return;
    try { document.dispatchEvent(new CustomEvent("hb:open-card", { detail: { id } })); } catch (_) {}
    close();
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

  const load = async () => {
    setLoaded(false); pages.clear();
    const r = await api.getWidgetsRegistry();
    const byName = (a, b) => String(a.name || a.id).localeCompare(String(b.name || b.id));
    const list = ((r && r.registry) || []).filter(w => w && w.surface === "user" && w.id).sort(byName);
    setRows(list); setLoaded(true);
    const keep = list.find(w => w.id === sel());
    const first = keep || list.find(w => w.origin === "builtin") || list[0];
    if (first) select(first.id); else { setSel(null); setPage(null); }
    setTimeout(() => { const b = listEl && listEl.querySelector(".aw-row.is-selected"); if (b) b.focus(); }, 0);
  };

  // ── the list: rows are built once per load and only their CLASS follows the selection. Rebuilding a row between
  // the two clicks of a double click would swap the node under the pointer and the dblclick would never fire.
  const row = (w) => h("button", {
      class: () => "aw-row" + (sel() === w.id ? " is-selected" : ""), "data-app": w.id, role: "option",
      "aria-selected": () => (sel() === w.id ? "true" : "false"), title: () => t("appsWin.hint"),
      onClick: () => select(w.id),
      onDblClick: () => openApp(w.id),
      onKeyDown: (e) => { if (e.key === "Enter") { e.preventDefault(); openApp(w.id); } },
    },
    h("span", { class: "aw-icon" }, raw(APPS_ICON)),
    h("span", { class: "aw-name" }, w.name || w.id));

  const listBody = () => {
    if (!loaded()) return [h("div", { class: "hb-empty-state" }, () => t("appsWin.loading"))];
    const all = rows();
    if (!all.length) return [h("div", { class: "hb-empty-state" }, () => t("appsWin.empty"))];
    const sys = all.filter(w => w.origin === "builtin"), mine = all.filter(w => w.origin !== "builtin");
    const out = [];
    if (sys.length) out.push(h("div", { class: "hb-sectitle aw-group" }, () => t("chat.appsSystem")), ...sys.map(row));
    if (mine.length) out.push(h("div", { class: "hb-sectitle aw-group" }, () => t("chat.appsCustom")), ...mine.map(row));
    return out;
  };

  const onListKey = (e) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const btns = [...listEl.querySelectorAll(".aw-row")];
    const i = btns.findIndex(b => b.dataset.app === sel());
    const next = btns[Math.max(0, Math.min(btns.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))];
    if (next) { e.preventDefault(); next.focus(); select(next.dataset.app); }
  };

  // ── the page: ONLY the keys the server sent. Each block carries `data-field` so a reader (and the test) can tell
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
        h("button", { class: "hb-btn hb-btn--primary aw-open", onClick: () => openApp(p.id) }, t("appsWin.open"))),
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
                   ref: (n) => (listEl = n), onKeyDown: onListKey }, () => listBody()),
        h("article", { class: "aw-page" }, () => pageBody()))));

  let wasOpen = false;
  createEffect(() => { const o = store.appsWindowOpen(); if (o && !wasOpen) load(); wasOpen = o; });
  return el;
}
