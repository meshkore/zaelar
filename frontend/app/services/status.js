// ============================================================================
// status.js — polls /api/status into the store so the ◉ icon reflects live
// system health (Hermes, LLM/STT/TTS credit, cluster) even with the panel closed.
//
// TWO sources of truth, merged so the panel is PRECISE:
//   · SERVER (/api/status) — the pieces only the server knows (Hermes up, model
//     credit, cluster). If the fetch FAILS (server restarting/crashed) we surface
//     a RED "server not responding" → the ◉ blinks red immediately (no stale green).
//   · CLIENT (this browser) — the VOICE row. The server's `active.count()` is the
//     old Pipecat registry and is never updated by the LiveKit engine, so it always
//     said "en espera". The browser is the ONLY thing that truly knows if voice is
//     live: LiveKit connection state + mic availability (mic busy/denied → red).
// The ◉ icon's color/blink = overallStatus() = worst(server, client-voice, offline).
// ============================================================================
import * as api from "./api.js?v=2";
import * as store from "../core/store.js?v=2";
import { t } from "../core/i18n.js?v=1";

const SEV = { ok: 0, off: 0, unknown: 1, warn: 2, error: 3 };   // "off" (voice idle) is NON-alarming
const LABEL = ["ok", "unknown", "warn", "error"];

// The VOICE row, computed from THIS browser's live signals (reactive: reads store signals).
export function voiceStatus() {
  const mb = store.micBlocked();
  if (mb && mb.show) return { state: "error", detail: mb.msg || t("statussvc.mic_unavailable") };
  const conn = store.conn() || {};
  const reconnecting = /reconnect|reconect/i.test(conn.label || "");
  if (store.started()) {
    if (reconnecting) return { state: "warn", detail: t("statussvc.reconnecting") };
    if (!conn.ok) return { state: "warn", detail: t("statussvc.connecting") };
    return { state: "ok", detail: store.micMuted() ? t("statussvc.active_mic_muted") : t("statussvc.active_listening") };
  }
  if (store.starting()) return { state: "warn", detail: t("statussvc.connecting") };
  return { state: "off", detail: t("statussvc.standby") };
}

// Worst of: server overall, this browser's voice state, and the offline flag. Drives the ◉ icon (color + blink).
export function overallStatus() {
  const s = store.status() || {};
  if (s.offline) return "error";
  const worst = Math.max(SEV[s.overall] ?? 1, SEV[voiceStatus().state] ?? 0);
  return LABEL[worst] || "ok";
}

export async function refreshStatus() {
  try {
    store.setStatus(await api.getStatus());
    // API balances (V2-043): the server caches the probe (TTL) → calling it every 15s is cheap. Credit alerts
    // (warn/error) feed the status dialog even if settings has never been opened.
    try { const a = await api.getApiSummary(false); store.setApiSummary(a.apis || []); store.setApiAlerts(a.alerts || []); } catch (_) {}
  } catch (_) {
    // Server unreachable (restarting / crashed) → RED alarm now, don't keep a stale green.
    store.setStatus({
      overall: "error", offline: true,
      items: [{ key: "server", label: t("statussvc.server_label"), state: "error", detail: t("statussvc.server_not_responding") }],
    });
  }
}

let _iv = null;
export function startStatusPolling(ms = 15000) {
  refreshStatus();
  if (_iv) clearInterval(_iv);
  _iv = setInterval(refreshStatus, ms);
}
