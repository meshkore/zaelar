// StatusPanel — system health at a glance. Toggled by the ◉ status button in the TopBar (store.statusOpen).
// Lists each subsystem (Hermes · voz · LLM · STT · TTS · cluster) with a colored dot and a one-line detail, so a
// problem — no saldo/cuota, credencial inválida, Hermes caído, cluster desconectado — is visible and explained.
// The data is polled into store.status() by services/status.js (also refreshed on SSE alert/error for an instant
// red). This panel just renders it and offers a manual ⟳ refresh.
import { h, raw } from "../core/dom.js?v=2";
import { createEffect } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import { refreshStatus, voiceStatus } from "../services/status.js?v=2";
import { makeDraggable } from "../lib/draggable.js?v=2";
import { ACTIVITY_ICON, REFRESH_ICON, CLOSE_ICON } from "../lib/icons.js?v=1";
import { t } from "../core/i18n.js?v=1";

// Status DOT class: a plain CSS circle (see .st-dot in styles.css), colored via --hb-ok/--hb-warn/--hb-risk —
// ONE mechanism, shared with the ◉ TopBar button, instead of a separate 🟢🟡🔴⚪ emoji-only palette.
const DOT_CLS = { ok: "st-dot-ok", warn: "st-dot-warn", error: "st-dot-error", off: "", unknown: "" };
const OVERALL = { ok: "status.overall_ok", warn: "status.overall_warn", error: "status.overall_error", unknown: "status.overall_checking" };
// 9-dot grip — same affordance as the camera unit's move handle, so this panel drags like any other widget.
const DRAG_SVG = `<svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor"><circle cx="2.5" cy="2.5" r="1.3"/><circle cx="7" cy="2.5" r="1.3"/><circle cx="11.5" cy="2.5" r="1.3"/><circle cx="2.5" cy="7" r="1.3"/><circle cx="7" cy="7" r="1.3"/><circle cx="11.5" cy="7" r="1.3"/><circle cx="2.5" cy="11.5" r="1.3"/><circle cx="7" cy="11.5" r="1.3"/><circle cx="11.5" cy="11.5" r="1.3"/></svg>`;

export function StatusPanel() {
  createEffect(() => { if (store.statusOpen()) refreshStatus(); });   // fresh read whenever it opens
  let panelEl, gripEl;

  const row = (it, secondary) => h("div", { class: "st-row st-" + (it.state || "unknown") + (secondary ? " st-2" : "") },
    h("span", { class: "st-dot " + (DOT_CLS[it.state] || "") }),
    h("div", { class: "st-main" },
      h("div", { class: "st-name" }, it.label || it.key),
      h("div", { class: "st-detail" }, it.detail || ""),
    ),
  );
  const sec = (txt, cls) => h("div", { class: "st-sec" + (cls ? " " + cls : "") }, txt);

  const panel = h("div", { class: () => "statuspanel" + (store.statusOpen() ? " open" : ""), ref: (el) => (panelEl = el) },
    h("div", { class: "cw-head" },
      h("button", { class: "cw-grip", ref: (el) => (gripEl = el), title: () => t("status.move") }, raw(DRAG_SVG)),
      h("span", { class: "cw-title" }, raw(ACTIVITY_ICON), () => t("status.title") + " · " + (OVERALL[store.status().overall] ? t(OVERALL[store.status().overall]) : "")),
      h("button", { class: "cw-x hb-icbtn", title: () => t("status.refresh"), onClick: refreshStatus }, raw(REFRESH_ICON)),
      h("button", { class: "cw-x hb-icbtn", title: () => t("status.close"), onClick: () => store.setStatusOpen(false) }, raw(CLOSE_ICON)),
    ),
    h("div", { class: "st-list" },
      () => {
        // VOICE row is CLIENT-authoritative (the server's active.count() never sees the LiveKit session): override
        // it with this browser's live state, and inject one if the server didn't send it (e.g. server offline).
        let items = (store.status().items || []).map((it) => (it.key === "voice" ? { ...it, ...voiceStatus() } : it));
        if (!items.some((it) => it.key === "voice")) {
          items = [...items, { key: "voice", label: "Voice system", group: "core", ...voiceStatus() }];
        }
        if (!items.length) return h("div", { class: "cron-empty" }, () => t("status.checking"));
        const core = items.filter((it) => (it.group || "core") === "core");
        const extra = items.filter((it) => it.group === "extra");
        const out = [sec(() => t("status.sec_core")), ...core.map((it) => row(it))];
        if (extra.length) out.push(sec(() => t("status.sec_secondary"), "st-sec-2"), ...extra.map((it) => row(it, true)));
        // Alertas de SALDO (V2-043): solo las APIs en warn/error (crédito agotado / credencial / caída). Los
        // importes completos viven en el área de configuración (⚙ · resumen de APIs). Nada si no hay alertas.
        const alerts = store.apiAlerts() || [];
        if (alerts.length) {
          out.push(sec(() => t("status.sec_apis"), "st-sec-2"),
            ...alerts.map((a) => row({ key: a.key, label: a.key, state: a.state, detail: a.detail || t("status.check_balance") }, true)));
        }
        return out;
      },
    ),
  );
  // Drag ONLY by the grip (matches the camera unit); position persists per-browser.
  makeDraggable(panelEl, gripEl, "hb_pos_status", "tl");
  return panel;
}
