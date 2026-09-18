// TopBar — top-right PROJECT controls, left to right: ◉ status · ◷ debug · 🖥 daemon · 👤 account (cloud) ·
// 🧠 memory · ☾ theme · 🧭 setup · ⚙ settings · Reset.
// These are the project's tools; zaelar's OWN things (voice, memory, captions, crons, attention, power, theme)
// live on the EYE's upper lid over the orb (Orb.js, V2-039 “ojo”). ⏰ cron moved there in V2-014; ☾/☀ theme moved
// there in V2-039. The voice session is ALWAYS ON (auto-connects, main.js) — the ⏻ icon on the eye is the one
// explicit, persisted exception. Reset clears the canvas. (operator 2026-07-07)
import { h, raw } from "../core/dom.js?v=2";
import * as store from "../core/store.js?v=2";
import * as session from "../services/session.js?v=3";
import * as api from "../services/api.js?v=2";
import { overallStatus } from "../services/status.js?v=2";
import { toggleTheme } from "../services/theme.js?v=2";
import { t } from "../core/i18n.js?v=1";
import { BUG_ICON, GEAR_ICON, COMPASS_ICON, MOON_ICON, USER_ICON, MEM_ICON, DESKTOP_ICON } from "../lib/icons.js?v=2";
import * as daemon from "../services/daemon.js?v=1";
import { EnergyGauge } from "./EnergyGauge.js?v=1";

// Status dot is a plain filled circle (see .statusBtn svg below) — recolors via the SAME --hb-ok/--hb-warn/--hb-risk
// tokens the rest of the app uses for health state, instead of a one-off emoji/dingbat only this button had.
const STATUS_ICON = `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="7" fill="currentColor"/></svg>`;

export function TopBar() {
  return h("div", { class: "tr" },
    // System status: the health beacon lives at the LEFT extreme of the toolbar. A dot that greens/ambers/reds
    // (blinks on error) so a problem (no saldo, Hermes caído, cluster desconectado) grabs attention without
    // opening anything. Click → the status panel with the per-item detail.
    // CLOUD (cuenta of pago): the header se reduce a PERFIL + tema. En cuanto /api/config dice cloud_profile (=
    // ZAELAR_USER_ID puesto) se ocultan estado/observabilidad/config/wizard/reset. En self-host cloudProfile es
    // false and the header no cambia (cero regresión). The gate es reactivo: si the config tarda, aparecen and se ocultan.
    () => store.cloudProfile() ? null : h("button", {
      class: () => "ic statusBtn st-" + overallStatus(),   // worst(server, voz of the browser, offline) → color + parpadeo
      id: "statusBtn", title: () => t("topbar.status.title"),
      onClick: () => { const v = !store.statusOpen(); store.setStatusOpen(v); api.uiEvent("topbar:status", { state: v ? "open" : "close" }); },
    }, raw(STATUS_ICON)),
    () => store.cloudProfile() ? null : h("button", {
      class: () => "ic" + (store.debugOpen() ? " on" : ""),
      id: "debugBtn", title: () => t("topbar.debug.title"),
      onClick: () => { const v = !store.debugOpen(); store.setDebugOpen(v); api.uiEvent("topbar:debug", { state: v ? "open" : "close" }); },
    }, raw(BUG_ICON)),
    // ☾ tema: MOVIDO here from the ojo (Orb.js, 2026-08-09) — junto a ⚙, a operator request. ONE icon (moon),
    // blue=dark/grey=light — mismo lenguaje on/off that the resto of controles, nunca se cambia by un icono of sol.
    // LA PILA of Energy, pegada a the IZQUIERDA of the 👤 (EnergyGauge.js, 2026-08-13). Se gatea sola by the `cloud` de
    // /api/energy and NO by `cloudProfile`: es the mismo hecho by dos vías, and the pila tiene that creerle al endpoint
    // that le da the saldo, no a otro. En self-host devuelve null and here no aparece nada.
    // 🖥 THE LOCAL DAEMON (V2-575 P1). The one icon here that is NOT gated on `cloudProfile`, and that is the
    // whole point of it: a cloud account is precisely the case where the user's own computer is unreachable —
    // no window to open, no CAPTCHA to pass, no documents — and this is where they get the installer for it.
    // Hiding it in cloud would hide it from the only people who cannot solve the problem any other way.
    // Same visual language as the ◉ (`.st-ok/.st-warn`), because it answers the same shape of question.
    h("button", {
      class: () => "ic daemonBtn st-" + daemon.iconState() + (store.daemonSetupOpen() ? " on" : ""),
      id: "daemonBtn", title: () => t("topbar.daemon.title"),
      onClick: () => { const v = !store.daemonSetupOpen(); store.setDaemonSetupOpen(v); api.uiEvent("topbar:daemon", { state: v ? "open" : "close" }); },
    }, raw(DESKTOP_ICON)),
    EnergyGauge(),
    // 👤 Perfil of the CUENTA (SOLO cloud): the data of the cuenta of pago (usuario/energía/plan) — distinto of la
    // persona of the operador, that vive en the orbe. En self-host NO aparece (instalación puramente local, no hace falta).
    // Contenido by definir; hoy abre un panel placeholder.
    () => store.cloudProfile() ? h("button", { class: () => "ic" + (store.accountOpen() ? " on" : ""), id: "acctBtn",
      title: () => t("topbar.account.title"),
      onClick: () => { const v = !store.accountOpen(); store.setAccountOpen(v); api.uiEvent("topbar:account", { state: v ? "open" : "close" }); } }, raw(USER_ICON)) : null,
    // 🧠 memory map — MOVED here from the orb's upper lid (V2-623, operator 2026-09-08: «quita el icono de la
    // memoria del orbe. ponlo arriba a la derecha»). Same signal, same viewer; only the button's home changed.
    h("button", { class: () => "ic" + (store.memOpen() ? " on" : ""), id: "memBtn",
      title: () => t("orb.memory"),
      onClick: () => { const v = !store.memOpen(); store.setMemOpen(v); api.uiEvent("topbar:memory", { state: v ? "open" : "close" }); } }, raw(MEM_ICON)),
    h("button", { class: () => "ic" + (store.theme() === "dark" ? " on" : ""), id: "themeBtn",
      title: () => (store.theme() === "dark" ? t("topbar.theme_light") : t("topbar.theme_dark")),
      onClick: () => { toggleTheme(); api.uiEvent("topbar:theme", { state: store.theme() }); } }, raw(MOON_ICON)),
    // 🧭 Setup panel (V2-040): what is MISSING on this machine + its API keys. It no longer asks where it is
    // running and no longer fires on its own at first boot (V2-671, V2-725) — this icon is its only door.
    () => store.cloudProfile() ? null : h("button", { class: () => "ic" + (store.wizardOpen() ? " on" : ""), id: "wizBtn",
      title: () => t("topbar.wizard.title"),
      onClick: () => { const v = !store.wizardOpen(); store.setWizardOpen(v); api.uiEvent("topbar:wizard", { state: v ? "open" : "close" }); } }, raw(COMPASS_ICON)),
    // ⚙ SETTINGS — the LAST icon of the row, immediately left of Reset (V2-725, operator: «pon el icono de
    // configuración a la derecha del todo como en todas las aplicaciones del mundo… el siguiente icono que
    // aparece a su lado a la izquierda debe ser el de configuración»). It used to sit third from the left,
    // between the bug and the daemon, which put the one control people look for by habit in the middle of a
    // row of controls they do not. Reset is the only thing to its right, and Reset is temporary chrome.
    // Badge rojo (2026-08-03): store.apiAlerts() ya alimenta the ◉ of estado; the mismo dato here porque ⚙ es donde
    // the operador mira the detalle by proveedor (workers/cluster relevados, saldo agotado…) — no un aviso nuevo.
    () => store.cloudProfile() ? null : h("button", { class: () => "ic" + (store.configOpen() ? " on" : ""), id: "cfgBtn",
      title: () => t("topbar.settings.title"),
      onClick: () => { const v = !store.configOpen(); store.setConfigOpen(v); api.uiEvent("topbar:settings", { state: v ? "open" : "close" }); } },
      raw(GEAR_ICON), () => ((store.apiAlerts() || []).length ? h("span", { class: "ic-badge" }) : null)),
    // Reset = DESTRUCTIVO: for todos the procesos of fondo and limpia the canvas. Pide confirmación primero.
    () => store.cloudProfile() ? null : h("button", { class: "reset", id: "reset", title: () => t("topbar.reset.title"),
      onClick: () => { api.uiEvent("topbar:reset", { state: "prompt" }); store.setResetConfirmOpen(true); } }, () => t("topbar.reset")),
    ResetConfirm(),
    RestartingOverlay(),
    AccountPanel(),
  );
}

// Diálogo of confirmación of the Reset — CON CHECKBOXES (V2-063, operator request 2026-07-23). Overlay modal
// (NO un toast). The BASE (siempre, without marcar nada): for the procesos of fondo, limpia observabilidad And deja el
// escritorio en blanco — LIVE, without reiniciar (lo that antes era the único comportamiento of the botón). Dos checkboxes
// OPCIONALES, desmarcados by defecto (como pidió the operador — "como si outside un user that empieza of cero"
// sería marcarlos TÚ, no the default): "Memoria" (state+corto+largo plazo, un only botón) and "Credenciales de
// widgets" (WhatsApp/Telegram/navegador). Marcar cualquiera of the dos exige that the server se reinicie solo
// (SQLite/perfiles en uso) — `session.resetFull()` lo gestiona and pinta the overlay of "reiniciando…".
function ResetConfirm() {
  let memEl, credEl, profEl, filesEl;
  const close = () => store.setResetConfirmOpen(false);
  const confirm = () => {
    const wipeMemory = !!(memEl && memEl.checked);
    const wipeCredentials = !!(credEl && credEl.checked);
    // V2-670: the two the operator asked for after measuring that ticking the first two still left an agent
    // speaking his language with his voice — `stt_language` survived in settings.json, and it IS the gate.
    const wipeProfile = !!(profEl && profEl.checked);
    const wipeFiles = !!(filesEl && filesEl.checked);
    close();
    session.resetFull({ wipeMemory, wipeCredentials, wipeProfile, wipeFiles });
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
      h("label", { class: "rc-check" },
        h("input", { type: "checkbox", ref: (el) => (profEl = el) }),
        " ", () => t("reset.confirm.wipeProfile")),
      h("label", { class: "rc-check" },
        h("input", { type: "checkbox", ref: (el) => (filesEl = el) }),
        " ", () => t("reset.confirm.wipeFiles")),
      h("p", { class: "rc-body rc-hint" }, () => t("reset.confirm.hint")),
      h("div", { class: "rc-actions" },
        h("button", { class: "rc-btn rc-no", onClick: close }, () => t("reset.confirm.cancel")),
        h("button", { class: "rc-btn rc-yes", onClick: confirm }, () => t("reset.confirm.yes")),
      ),
    ),
  );
  return ovl;
}

// Panel of CUENTA (icono 👤, only cloud). Reutiliza the overlay of the Reset (`ovl rc-ovl` + `rc-box`) para
// no añadir CSS. Balance/plan/facturación en detalle no se muestran AQUÍ (eso pediría un endpoint propio del
// motor); this panel es only the punto of salida — un enlace of vuelta a where esos data SÍ viven. The URL es un
// literal fijo, no a env var: no depende of qué despliegue sea, así that no hace falta configurarlo.
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
        h("a", {
          class: "rc-btn rc-yes",
          href: "https://zaelar.com/account",
          target: "_blank",
          rel: "noopener",
        }, () => t("account.manage")),
        h("button", { class: "rc-btn rc-no", onClick: close }, () => t("account.close")),
      ),
    ),
  );
  return ovl;
}

// Overlay of "reiniciando…" (V2-063) — se pinta mientras `session.resetFull()` espera a that the server vuelva a
// responder tras un reinicio automático (checkbox Memoria/Credenciales marcado). Recarga the página sola al volver.
function RestartingOverlay() {
  return h("div", { class: () => "ovl rc-ovl" + (store.restarting() ? " on" : "") },
    h("div", { class: "rc-box" },
      h("h3", { class: "rc-title" }, () => t("restarting.title")),
      h("p", { class: "rc-body" }, () => t("restarting.body")),
    ),
  );
}
