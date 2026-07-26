// ============================================================================
// api.js — thin fetch wrappers over the zaelar HTTP backend. No state, no UI.
// Migrates to any framework unchanged. Every call is best-effort (callers decide
// how to react); errors are swallowed where the original inline code swallowed them.
// ============================================================================

const json = (r) => r.json();
const postJSON = (url, body, opts = {}) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), ...opts });

// ---- voice / session config ----
export const setVoiceConfig = (voice) => postJSON("/config", { voice }).catch(() => {});
export const sendOffer = (sdp) => postJSON("/api/offer", { sdp: sdp.sdp, type: sdp.type });
export const hangup = () => { try { fetch("/api/hangup", { method: "POST", keepalive: true }); } catch (_) {} };
export const reset = () => fetch("/reset", { method: "POST" }).catch(() => {});
// HARD reset (botón Reset, tras confirmación): congela el trabajo en curso en la memoria de estado, lo registra
// en corto plazo y MATA los procesos de fondo (navegador/escaladas/notas) — ver server /reset/hard + nucleo/reset.py.
export const resetHard = () => fetch("/reset/hard", { method: "POST" }).then(r => r.json()).catch(() => ({}));
// Reset CON CHECKBOXES (V2-063): {wipe_memory, wipe_credentials} además de la base de siempre (observabilidad +
// escritorio). Si cualquiera de los dos es true, el server se reinicia solo — ver server/voice_api.py.
export const resetFull = (opts = {}) => postJSON("/api/reset/full", opts).then(r => r.json()).catch(() => ({}));
// V2-065 (botón ⏻ del ojo): congela/reanuda los Brain Workers vivos SIN matarlos (SIGSTOP/SIGCONT) — reversible,
// a diferencia de resetHard. Ver server/voice_api.py + nucleo/dispatch.py::pause_all/resume_all.
export const workersPause = () => fetch("/api/workers/pause", { method: "POST" }).then(r => r.json()).catch(() => ({}));
export const workersResume = () => fetch("/api/workers/resume", { method: "POST" }).then(r => r.json()).catch(() => ({}));

export async function iceServers() {
  let servers = [{ urls: "stun:stun.l.google.com:19302" }];
  try { const ic = await fetch("/api/ice-servers").then(json); if (ic.iceServers && ic.iceServers.length) servers = ic.iceServers; } catch (_) {}
  return servers;
}
export const sttMode = () => fetch("/api/stt-mode").then(json);
// LiveKit engine (INI-012): fetch a room-join token {token, url, room}.
export const lkToken = () => fetch("/api/token").then(json);

// UNA SOLA SESIÓN DE VOZ VIVA POR MÁQUINA (2026-07-12): el server es el árbitro (localhost = mismo ordenador).
// acquire/heartbeat devuelven {ok}: ok=false → otra pestaña/navegador está viva. Fail-open ante error de red
// (si el server no responde no hay sesión con la que chocar → no bloquees al usuario). release por sendBeacon
// al cerrar la pestaña (best-effort, sobrevive al unload).
export const sessionAcquire = (sid) => postJSON("/api/session/acquire", { sid }).then(json).catch(() => ({ ok: true }));
export const sessionHeartbeat = (sid) => postJSON("/api/session/heartbeat", { sid }).then(json).catch(() => ({ ok: true }));
export const sessionRelease = (sid) => {
  try {
    const blob = new Blob([JSON.stringify({ sid })], { type: "application/json" });
    if (navigator.sendBeacon && navigator.sendBeacon("/api/session/release", blob)) return;
  } catch (_) {}
  try { fetch("/api/session/release", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sid }), keepalive: true }); } catch (_) {}
};
export const voices = () => fetch("/api/voices").then(json).catch(() => ({}));
// ▶ test button: synthesize a SAMPLE for a provider+voice (does not touch the live session). Resolves to a
// playable audio Blob; rejects with the server message so the caller can surface why a voice couldn't be tried.
export const testVoice = (provider, voice, text = "") =>
  postJSON("/api/test-voice", { provider, voice, text }).then(async (r) => {
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || ("HTTP " + r.status));
    return r.blob();
  });

// ---- settings panel ----
export const getSettings = () => fetch("/api/settings").then(json);
export const saveSettings = (payload) => postJSON("/api/settings", payload).then(json);

// ---- diagnostics ----
export const clientLog = (label, o) => { try { postJSON("/api/client-log", { label, ...o }); } catch (_) {} };

// ---- observabilidad del frontend (V2-039): audita lo que TOCA el operador — iconos del orbe/TopBar (kind "ui") y
// geometría de widgets a mano (mover/redimensionar, kind "widget"). Fire-and-forget; el server estampa src="user". ----
export const uiEvent = (action, o = {}) => { try { postJSON("/api/ui-event", { action, ...o }); } catch (_) {} };

// ---- canvas → ESTADO (contexto de UI vivo) ----
// Reporta qué widgets tiene ABIERTOS el operador para que viajen en el prompt del cerebro (ESTADO) y se vean en el
// mapa de memoria. Best-effort, fire-and-forget: el canvas es la fuente de verdad, el servidor solo la refleja.
export const postCanvasState = (open) => { try { postJSON("/api/canvas/state", { open: open || [] }); } catch (_) {} };

// ---- widgets bridge (catalog identify; the desktop owns the rest) ----
export async function identifyWidget(text) {
  try { const r = await fetch("/widgets/identify?q=" + encodeURIComponent(text)).then(json); return r.match || null; } catch (_) { return null; }
}

// ---- brain identity ----
export const activeBrain = () => fetch("/api/brain").then(json).catch(() => ({ brain: "nucleo" }));

// ---- system status (ⓘ panel: cerebro/voz/LLM/STT/TTS/cluster + credit/health) ----
export const getStatus = () => fetch("/api/status").then(json).catch(() => ({ overall: "unknown", items: [] }));

// ---- memory map (🧠 visualizer: state + short/long-term memories + concept graph, read-only, no-cache) ----
export const getMemoryMap = () =>
  fetch("/api/memory/map", { cache: "no-store" }).then(json).catch(() => ({ state: {}, layers: { short: [], long: [] }, edges: [], counts: {} }));

// ---- proactive tasks/reminders (loop orquestador propio, nucleo/scheduler.py) ----
export const cronList = () => fetch("/api/cron").then(json).catch(() => ({ jobs: [] }));
export const cronAction = (action, ref) => postJSON("/api/cron/" + action, { ref }).then(json).catch(() => ({ ok: false }));
export const cronCreate = (body) => postJSON("/api/cron/create", body).then(json).catch(() => ({ ok: false }));

// ---- wizard de primer arranque (perfiles local/cloud + detector de capacidades, V2-040) ----
export const wizardState = () => fetch("/api/wizard/state", { cache: "no-store" }).then(json);
export const wizardReport = (refresh = true) => postJSON("/api/wizard/report", { refresh }).then(json);
export const wizardProfile = (name) => postJSON("/api/wizard/profile", { name }).then(json);
export const wizardCredential = (body) => postJSON("/api/wizard/credential", body).then(json);
export const wizardInstall = (body) => postJSON("/api/wizard/install", body).then(json);
export const wizardInstallStatus = (job) => fetch("/api/wizard/install/" + encodeURIComponent(job)).then(json);
export const wizardComplete = (done = true) => postJSON("/api/wizard/complete", { done }).then(json);

// ---- área de configuración full-screen + saldos de APIs (V2-043) ----
export const getConfig = () => fetch("/api/config", { cache: "no-store" }).then(json);
export const saveConfigV2 = (section, patch) => postJSON("/api/config/v2", { section, patch }).then(json);
export const saveConfigCredential = (key, value) => postJSON("/api/config/credential", { key, value }).then(json);
export const getApiSummary = (refresh = false) =>
  fetch("/api/config/apis" + (refresh ? "?refresh=1" : ""), { cache: "no-store" }).then(json).catch(() => ({ apis: [], alerts: [] }));
export const getBenchmarks = () => fetch("/api/config/benchmarks", { cache: "no-store" }).then(json);
