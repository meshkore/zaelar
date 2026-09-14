// ============================================================================
// update/UpdateSurface.js — the one thing a person sees of the update channel on the CANVAS (V2-553; the
// always-visible version badge retired in V2-666).
//
// THE BAR (top, above everything). «Hay una versión nueva — pulsa para actualizar.» It appears only when
// the engine is serving frontend bytes this tab is not running (`watch.js` decides), so a backend-only
// update never interrupts anyone. Clicking anywhere on it reloads.
//
// V2-666 (operator, 2026-09-11): the always-on "v11" badge that used to sit at the bottom-left corner of
// the desk was retired from the scene — «quítalo de la escena… puedes meter la versión dentro del apartado
// de configuración». The build number is not gone, it moved: `ConfigPanel.js` reads the SAME `build`/`info`
// signals this module still exports from `watch.js` and shows the version in its header, visible only while
// Settings is open. This file keeps `startUpdateWatch()` running (unconditionally, below) so that signal
// stays live whether or not Settings has ever been opened this session.
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
import { stale, dismiss, applyUpdate, startUpdateWatch } from "./watch.js?v=1";

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
  `;
  document.head.appendChild(s);
}

export function UpdateSurface() {
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

  // A layout-neutral holder: the bar is position:fixed, so this div occupies nothing wherever `main.js`
  // mounts it. The version badge that used to live here moved into ConfigPanel.js (V2-666).
  return h("div", { id: "hb-update", style: { display: "contents" } }, bar);
}
