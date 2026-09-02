// ============================================================================
// update/UpdateSurface.js — the two things a person sees of the update channel (V2-553).
//
// ONE system surface, TWO fixed elements, because the operator asked for two and they answer different
// questions:
//
//   · THE BAR (top, above everything). «Hay una versión nueva — pulsa para actualizar.» It appears only
//     when the engine is serving frontend bytes this tab is not running (`watch.js` decides), so a
//     backend-only update never interrupts anyone. Clicking anywhere on it reloads.
//   · THE BADGE (bottom of the left column). The build number, always visible, updated LIVE — «even if the
//     browser has been open for three days, [the user] can see how that number has been going up». It is a
//     signal, not a control; clicking it just forces a check now.
//
// WHY THE BADGE IS ITS OWN FIXED ELEMENT and not a chip inside `WidgetRail.js`, which is the bar it visually
// belongs to: the rail hides itself whenever the canvas is empty (`refresh()` drops the `on` class), and a
// version number you can only read while a widget happens to be open is not a version number you can read.
// It sits in the rail's column and gets out of the way when the rail is FOLDED — that is what the
// `body:has(#wrail.folded)` rule is for, and it is why this file needs no reference to the rail at all.
//
// WHY THE BAR OWNS `--banner-h`: that custom property already existed in `core/palette.css`, documented as
// «height of the update banner when visible (0 when hidden) — top controls shift down by this», with `.tr`
// and `.me` already consuming it through a `calc()` and a 0.2 s transition. The seam was built for exactly
// this banner and had never had a writer. So the top-right toolbar and the camera unit slide down on their
// own, and nothing in `styles.css` had to change. Widget cards are untouched on purpose: placement already
// reserves the top 70 px (`Desktop.tile.top`), which is more than this bar occupies, so the V2-551
// guarantee that a card is always whole and reachable still holds with the bar up.
import { h } from "../core/dom.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import { t } from "../core/i18n.js?v=1";
import { build, stale, info, check, dismiss, applyUpdate, startUpdateWatch } from "./watch.js?v=1";

const BAR_H = 36;

function injectStyles() {
  if (document.getElementById("hb-upd-css")) return;
  const s = document.createElement("style");
  s.id = "hb-upd-css";
  s.textContent = `
  /* Above EVERYTHING: the highest z-index anywhere else in the app today is 100020 (the vault modal). */
  #hb-upd-bar{position:fixed;left:0;right:0;top:0;height:${BAR_H}px;z-index:100200;
    display:none;align-items:center;justify-content:center;gap:12px;cursor:pointer;padding:0 12px;
    background:var(--hb-accent,#3D6FE0);color:#fff;
    font:600 13px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
    box-shadow:0 2px 10px rgba(13,22,34,.28);animation:hbUpdIn .22s ease-out}
  #hb-upd-bar.on{display:flex}
  @keyframes hbUpdIn{from{transform:translateY(-100%)}to{transform:translateY(0)}}
  #hb-upd-bar .u-msg{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  #hb-upd-bar .u-go{flex:none;border:1px solid rgba(255,255,255,.55);border-radius:7px;background:rgba(255,255,255,.14);
    color:#fff;font:600 12px/1 inherit;padding:6px 10px;cursor:pointer}
  #hb-upd-bar .u-go:hover{background:rgba(255,255,255,.26)}
  #hb-upd-bar .u-x{flex:none;border:none;background:transparent;color:rgba(255,255,255,.8);
    font:600 15px/1 inherit;cursor:pointer;padding:6px 4px}
  #hb-upd-bar .u-x:hover{color:#fff}
  /* The version badge lives in the rail's 40px column, pinned to the bottom edge. */
  #hb-upd-ver{position:fixed;left:0;bottom:6px;width:40px;z-index:9003;
    display:flex;align-items:center;justify-content:center;cursor:default;
    font:600 10px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
    color:var(--hb-muted-2,#7d8a9c);opacity:.75;user-select:none}
  #hb-upd-ver:hover{opacity:1;color:var(--hb-ink,#e8edf5)}
  /* Folded rail = a 12px sliver the operator asked to get out of the way; the number goes with it. */
  body:has(#wrail.folded) #hb-upd-ver{display:none}
  `;
  document.head.appendChild(s);
}

// `badge:false` is for the MOBILE shell: its bottom edge belongs to the dock, so a version chip pinned there
// would sit on top of the controls. The phone gets the BAR — the surface most likely to be running stale code,
// since a PWA can stay installed and backgrounded for days — and no badge until there is a right place for one.
export function UpdateSurface({ badge: withBadge = true } = {}) {
  injectStyles();
  startUpdateWatch();

  const bar = h("div", {
    id: "hb-upd-bar",
    class: () => (stale() ? "on" : ""),
    // The whole bar is the target, not just the button: the operator described it as «pulsa aquí para
    // reiniciar el navegador», and a 36px-tall strip that is only clickable in one 60px spot is a strip
    // people click and nothing happens.
    onClick: applyUpdate,
  },
    h("span", { class: "u-msg" }, () => t("update.available")),
    h("button", { class: "u-go" }, () => t("update.action")),
    h("button", {
      class: "u-x",
      title: () => t("update.dismiss"),
      onClick: (e) => { e.stopPropagation(); dismiss(); },
    }, "✕"),
  );

  // The seam that already existed for this banner (see the header note). Written from here, and set back
  // to 0px on dismissal, so the top controls come back up.
  createEffect(() => {
    try {
      document.documentElement.style.setProperty("--banner-h", stale() ? BAR_H + "px" : "0px");
    } catch (_) { /* no CSSOM (harness): the bar still renders, the toolbar just does not shift */ }
  });

  const badge = h("div", {
    id: "hb-upd-ver",
    title: () => {
      const s = info() || {};
      return t("update.version_title", { short: s.short || "?", deploy: s.deploy || "?" });
    },
    onClick: check,   // a signal, not a control — the only thing it does is ask again, now

  }, () => {
    const n = build();
    if (n > 0) return "v" + n;
    const s = info() || {};
    return s.version ? "v" + s.version : "";
  });

  // A layout-neutral holder: both children are position:fixed, so this div occupies nothing wherever
  // `main.js` mounts it. One entry in SYSTEM_SURFACES, two surfaces.
  return h("div", { id: "hb-update", style: { display: "contents" } }, bar, withBadge ? badge : null);
}
