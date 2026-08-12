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
import { toggleTheme } from "../services/theme.js?v=2";
import { t } from "../core/i18n.js?v=1";
import { BUG_ICON, GEAR_ICON, COMPASS_ICON, MOON_ICON, USER_ICON } from "../lib/icons.js?v=1";

// Status dot is a plain filled circle (see .statusBtn svg below) — recolors via the SAME --hb-ok/--hb-warn/--hb-risk
// tokens the rest of the app uses for health state, instead of a one-off emoji/dingbat only this button had.
const STATUS_ICON = `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="7" fill="currentColor"/></svg>`;

export function TopBar() {
  return h("div", { class: "tr" },
    // System status: the health beacon lives at the LEFT extreme of the toolbar. A dot that greens/ambers/reds
    // (blinks on error) so a problem (no saldo, Hermes caído, cluster desconectado) grabs attention without
    // opening anything. Click → the status panel with the per-item detail.
    // CLOUD (cuenta de pago): el header se reduce a PERFIL + tema. En cuanto /api/config dice cloud_profile (=
    // ZAELAR_USER_ID puesto) se ocultan estado/observabilidad/config/wizard/reset. En self-host cloudProfile es
    // false y el header no cambia (cero regresión). El gate es reactivo: si la config tarda, aparecen y se ocultan.
    () => store.cloudProfile() ? null : h("button", {
      class: () => "ic statusBtn st-" + overallStatus(),   // worst(server, voz del browser, offline) → color + parpadeo
      id: "statusBtn", title: () => t("topbar.status.title"),
      onClick: () => { const v = !store.statusOpen(); store.setStatusOpen(v); api.uiEvent("topbar:status", { state: v ? "open" : "close" }); },
    }, raw(STATUS_ICON)),
    () => store.cloudProfile() ? null : h("button", {
      class: () => "ic" + (store.debugOpen() ? " on" : ""),
      id: "debugBtn", title: () => t("topbar.debug.title"),
      onClick: () => { const v = !store.debugOpen(); store.setDebugOpen(v); api.uiEvent("topbar:debug", { state: v ? "open" : "close" }); },
    }, raw(BUG_ICON)),
    // ☾/☀ theme MOVED to the orb's upper lid (V2-039 «ojo» — generic/personal control, helps close the eye shape).
    // Badge rojo (2026-08-03): store.apiAlerts() ya alimenta el ◉ de estado; el mismo dato aquí porque ⚙ es donde
    // el operador mira el detalle por proveedor (workers/cluster relevados, saldo agotado…) — no un aviso nuevo.
    () => store.cloudProfile() ? null : h("button", { class: () => "ic" + (store.configOpen() ? " on" : ""), id: "cfgBtn",
      title: () => t("topbar.settings.title"),
      onClick: () => { const v = !store.configOpen(); store.setConfigOpen(v); api.uiEvent("topbar:settings", { state: v ? "open" : "close" }); } },
      raw(GEAR_ICON), () => ((store.apiAlerts() || []).length ? h("span", { class: "ic-badge" }) : null)),
    // ☾ tema: MOVIDO aquí desde el ojo (Orb.js, 2026-08-09) — junto a ⚙, a petición del operador. ONE icon (moon),
    // blue=dark/grey=light — mismo lenguaje on/off que el resto de controles, nunca se cambia por un icono de sol.
    // 👤 Perfil de la CUENTA (SOLO cloud): los datos de la cuenta de pago (usuario/energía/plan) — distinto de la
    // persona del operador, que vive en el orbe. En self-host NO aparece (instalación puramente local, no hace falta).
    // Contenido por definir; hoy abre un panel placeholder.
    () => store.cloudProfile() ? h("button", { class: () => "ic" + (store.accountOpen() ? " on" : ""), id: "acctBtn",
      title: () => t("topbar.account.title"),
      onClick: () => { const v = !store.accountOpen(); store.setAccountOpen(v); api.uiEvent("topbar:account", { state: v ? "open" : "close" }); } }, raw(USER_ICON)) : null,
    h("button", { class: () => "ic" + (store.theme() === "dark" ? " on" : ""), id: "themeBtn",
      title: () => (store.theme() === "dark" ? t("topbar.theme_light") : t("topbar.theme_dark")),
      onClick: () => { toggleTheme(); api.uiEvent("topbar:theme", { state: store.theme() }); } }, raw(MOON_ICON)),
    // 🧭 Wizard de config (V2-040): perfil local/cloud + detector del sistema + credenciales. Se auto-abre en el
    // primer arranque; este icono lo reabre cuando el operador quiera revalidar/cambiar el perfil.
    () => store.cloudProfile() ? null : h("button", { class: () => "ic" + (store.wizardOpen() ? " on" : ""), id: "wizBtn",
      title: () => t("topbar.wizard.title"),
      onClick: () => { const v = !store.wizardOpen(); store.setWizardOpen(v); api.uiEvent("topbar:wizard", { state: v ? "open" : "close" }); } }, raw(COMPASS_ICON)),
    // Reset = DESTRUCTIVO: para todos los procesos de fondo y limpia el canvas. Pide confirmación primero.
    () => store.cloudProfile() ? null : h("button", { class: "reset", id: "reset", title: () => t("topbar.reset.title"),
      onClick: () => { api.uiEvent("topbar:reset", { state: "prompt" }); store.setResetConfirmOpen(true); } }, () => t("topbar.reset")),
    ResetConfirm(),
    RestartingOverlay(),
    AccountPanel(),
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

// Panel de CUENTA (icono 👤, solo cloud) — placeholder. Reutiliza el overlay del Reset (`ovl rc-ovl` + `rc-box`) para
// no añadir CSS. El contenido real (usuario/energía/plan/facturación) se define más adelante; hoy solo existe la
// superficie para que el header cloud tenga su sitio de "datos de la cuenta", separado de la persona del orbe.
function AccountPanel() {
  const close = () => store.setAccountOpen(false);
  let ovl;
  ovl = h("div", {
    class: () => "ovl rc-ovl" + (store.accountOpen() ? " on" : ""),
    onClick: (e) => { if (e.target === ovl) close(); },
  },
    h("div", { class: "rc-box" },
      h("h3", { class: "rc-title" }, () => t("account.title")),
      h("p", { class: "rc-body" }, () => t("account.body")),
      h("div", { class: "rc-actions" },
        h("button", { class: "rc-btn rc-no", onClick: close }, () => t("account.close")),
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
