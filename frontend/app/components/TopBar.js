// TopBar — top-right PROJECT controls: ◉ status · ◷ debug · ⚙ settings · 🧭 wizard · Reset.
// These are the project's tools; zaelar's OWN things (voice, memory, captions, crons, attention, power, theme)
// live on the EYE's upper lid over the orb (Orb.js, V2-039 «ojo»). ⏰ cron moved there in V2-014; ☾/☀ theme moved
// there in V2-039. The voice session is ALWAYS ON (auto-connects, main.js) — the ⏻ icon on the eye is the one
// explicit, persisted exception. Reset clears the canvas. (operator 2026-07-07)
import { h, raw } from "../core/dom.js?v=2";
import * as store from "../core/store.js?v=2";
import * as session from "../services/session.js?v=3";
import * as api from "../services/api.js?v=2";
import { overallStatus } from "../services/status.js?v=2";
import { t } from "../core/i18n.js?v=1";
import { BUG_ICON, GEAR_ICON, COMPASS_ICON } from "../lib/icons.js?v=1";

// Status dot is a plain filled circle (see .statusBtn svg below) — recolors via the SAME --hb-ok/--hb-warn/--hb-risk
// tokens the rest of the app uses for health state, instead of a one-off emoji/dingbat only this button had.
const STATUS_ICON = `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="7" fill="currentColor"/></svg>`;

export function TopBar() {
  return h("div", { class: "tr" },
    // System status: the health beacon lives at the LEFT extreme of the toolbar. A dot that greens/ambers/reds
    // (blinks on error) so a problem (no saldo, Hermes caído, cluster desconectado) grabs attention without
    // opening anything. Click → the status panel with the per-item detail.
    h("button", {
      class: () => "ic statusBtn st-" + overallStatus(),   // worst(server, voz del browser, offline) → color + parpadeo
      id: "statusBtn", title: () => t("topbar.status.title"),
      onClick: () => { const v = !store.statusOpen(); store.setStatusOpen(v); api.uiEvent("topbar:status", { state: v ? "open" : "close" }); },
    }, raw(STATUS_ICON)),
    h("button", {
      class: () => "ic" + (store.debugOpen() ? " on" : ""),
      id: "debugBtn", title: () => t("topbar.debug.title"),
      onClick: () => { const v = !store.debugOpen(); store.setDebugOpen(v); api.uiEvent("topbar:debug", { state: v ? "open" : "close" }); },
    }, raw(BUG_ICON)),
    // ☾/☀ theme MOVED to the orb's upper lid (V2-039 «ojo» — generic/personal control, helps close the eye shape).
    h("button", { class: () => "ic" + (store.configOpen() ? " on" : ""), id: "cfgBtn",
      title: () => t("topbar.settings.title"),
      onClick: () => { const v = !store.configOpen(); store.setConfigOpen(v); api.uiEvent("topbar:settings", { state: v ? "open" : "close" }); } }, raw(GEAR_ICON)),
    // 🧭 Wizard de config (V2-040): perfil local/cloud + detector del sistema + credenciales. Se auto-abre en el
    // primer arranque; este icono lo reabre cuando el operador quiera revalidar/cambiar el perfil.
    h("button", { class: () => "ic" + (store.wizardOpen() ? " on" : ""), id: "wizBtn",
      title: () => t("topbar.wizard.title"),
      onClick: () => { const v = !store.wizardOpen(); store.setWizardOpen(v); api.uiEvent("topbar:wizard", { state: v ? "open" : "close" }); } }, raw(COMPASS_ICON)),
    // Reset = DESTRUCTIVO: para todos los procesos de fondo y limpia el canvas. Pide confirmación primero.
    h("button", { class: "reset", id: "reset", title: () => t("topbar.reset.title"),
      onClick: () => { api.uiEvent("topbar:reset", { state: "prompt" }); store.setResetConfirmOpen(true); } }, () => t("topbar.reset")),
    ResetConfirm(),
    RestartingOverlay(),
  );
}

// Diálogo de confirmación del Reset — CON CHECKBOXES (V2-063, petición del operador 2026-07-23). Overlay modal
// (NO un toast). La BASE (siempre, sin marcar nada): para los procesos de fondo, limpia observabilidad Y deja el
// escritorio en blanco — LIVE, sin reiniciar (lo que antes era el único comportamiento del botón). Dos checkboxes
// OPCIONALES, desmarcados por defecto (como pidió el operador — "como si fuera un usuario que empieza de cero"
// sería marcarlos TÚ, no el default): "Memoria" (state+corto+largo plazo, un solo botón) y "Credenciales de
// widgets" (WhatsApp/Telegram/navegador). Marcar cualquiera de los dos exige que el server se reinicie solo
// (SQLite/perfiles en uso) — `session.resetFull()` lo gestiona y pinta el overlay de "reiniciando…".
function ResetConfirm() {
  let memEl, credEl;
  const close = () => store.setResetConfirmOpen(false);
  const confirm = () => {
    const wipeMemory = !!(memEl && memEl.checked);
    const wipeCredentials = !!(credEl && credEl.checked);
    close();
    session.resetFull({ wipeMemory, wipeCredentials });
  };
  let ovl;
  ovl = h("div", {
    class: () => "ovl rc-ovl" + (store.resetConfirmOpen() ? " on" : ""),
    onClick: (e) => { if (e.target === ovl) close(); },
  },
    h("div", { class: "rc-box" },
      h("h3", { class: "rc-title" }, () => t("reset.confirm.title")),
      h("p", { class: "rc-body" }, () => t("reset.confirm.body")),
      h("label", { class: "rc-check" },
        h("input", { type: "checkbox", ref: (el) => (memEl = el) }),
        " ", () => t("reset.confirm.wipeMemory")),
      h("label", { class: "rc-check" },
        h("input", { type: "checkbox", ref: (el) => (credEl = el) }),
        " ", () => t("reset.confirm.wipeCredentials")),
      h("p", { class: "rc-body rc-hint" }, () => t("reset.confirm.hint")),
      h("div", { class: "rc-actions" },
        h("button", { class: "rc-btn rc-no", onClick: close }, () => t("reset.confirm.cancel")),
        h("button", { class: "rc-btn rc-yes", onClick: confirm }, () => t("reset.confirm.yes")),
      ),
    ),
  );
  return ovl;
}

// Overlay de "reiniciando…" (V2-063) — se pinta mientras `session.resetFull()` espera a que el server vuelva a
// responder tras un reinicio automático (checkbox Memoria/Credenciales marcado). Recarga la página sola al volver.
function RestartingOverlay() {
  return h("div", { class: () => "ovl rc-ovl" + (store.restarting() ? " on" : "") },
    h("div", { class: "rc-box" },
      h("h3", { class: "rc-title" }, () => t("restarting.title")),
      h("p", { class: "rc-body" }, () => t("restarting.body")),
    ),
  );
}
