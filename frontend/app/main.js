// ============================================================================
// main.js — interface entry point. Wires the services + mounts the components,
// then brings up the widget desktop and the always-on visualizer.
//
// Mount order matters: the components must exist (so #me, #orbwrap, #activity are
// in the DOM) BEFORE the Desktop is created — it reads those for placement and
// restores the user's open widgets into #activity.
// ============================================================================
import { h, mount, $ } from "./core/dom.js?v=2";
import { createEffect } from "./core/reactive.js?v=2";
import * as session from "./services/session.js?v=3";
import { openSSE } from "./services/sse.js?v=4";
import * as store from "./core/store.js?v=2";
import { startStatusPolling } from "./services/status.js?v=2";
import { initTheme } from "./services/theme.js?v=2";
import { initI18n, t } from "./core/i18n.js?v=1";

// NATIVE frontend SURFACES (untouchable SYSTEM widgets): the SINGLE CANONICAL LIST lives in
// core/system-surfaces.js — main.js MOUNTS them from there (with no duplicated list). `submitChat` is the only symbol
// from a component that main.js uses apart from mounting (the clipboard-paste handler).
import { submitChat } from "./components/ChatWall.js?v=5";
import { SYSTEM_SURFACES } from "./core/system-surfaces.js?v=3";
import * as api from "./services/api.js?v=2";

import { Desktop } from "./widgets/desktop.js?v=5";

// ---- theme (dark/light) — apply before mounting anything, so nothing flashes the wrong palette ----
initTheme();
// ---- active UI language (V2-089): the store is seeded instantly from the localStorage mirror; reconcile with the
// backend's active language (ZAELAR_LANGUAGE). t() is reactive, so any correction re-renders the UI in place. ----
initI18n();

// ---- #desk = THE DESKTOP as ONE single unit (V2-062) — the "central column" of the 3-column layout.
// The entire desktop (backdrop, widgets, camera, orb, TopBar, status) lives INSIDE. When chat docks to an
// edge, #desk shrinks on that side (CSS: left/right = --chatdock-*, with `transform` making it a containing block)
// → ALL its position:fixed children are repositioned relative to #desk and move TOGETHER, including those with
// dragged inline positions (orb, camera) that the per-element offset could NOT move. Overlays/panels/modals
// and chat itself are mounted OUTSIDE #desk (at body level), above it. ----
const desk = mount(h("div", { id: "desk" }));

// ---- static scaffold (backdrop, widget stage, bot audio sink) ----
mount(h("div", { class: "canvas" }), desk);
// PHASE-scaffold system surfaces (today: the activity honeycomb) — go just above .canvas and BELOW the
// widget stage (V2-039: everything paints above the honeycomb). They are mounted from the canonical list.
for (const s of SYSTEM_SURFACES.filter(s => s.phase === "scaffold")) mount(s.comp(), desk);
mount(h("div", { class: "wstage", id: "wstage" }), desk);   // widgets pop onto the canvas here
const botAudio = mount(h("audio", { id: "botaudio", autoplay: true }));
session.attachBotAudio(botAudio);
// Reactive icon↔audio binding: <audio> ALWAYS reflects botMuted() (the same state painted by the bowl's 🔊 icon)
// — the on/off switch applies instantly and never leaves "muted icon but still playing" (V2-043 startup bug).
createEffect(() => { try { botAudio.muted = store.botMuted(); } catch (_) {} });

// ---- SYSTEM SURFACES (native, untouchable) — mounted from the SINGLE CANONICAL LIST
// (core/system-surfaces.js), in its stacking order. desktop chrome → #desk (moves when chat docks);
// panels/overlays/modals/chat/banners → body (above it). Adding a native surface = adding it to
// that list; nothing is changed here. EVERYTHING ELSE shown on screen is a USER widget (catalog
// widgets/<id>/, even when distributed by default) — variable, created by/for the user, like connectors. ----
for (const s of SYSTEM_SURFACES.filter(s => s.phase === "overlay")) {
  mount(s.comp(), s.target === "desk" ? desk : undefined);
}

// ---- first startup: if the config is not validated, open the wizard BEFORE anything else (config managed by the UI) ----
api.wizardState().then(s => { if (s && s.first_run) store.setWizardOpen(true); }).catch(() => {});

// The inline splash (#preboot in index.html) has served its purpose (loader from the FIRST byte); the modules have
// loaded and BootOverlay (neuron veil) takes over → remove it to avoid overlapping two loaders. If main.js
// had failed to load, #preboot remains (a loader is better than a black screen).
try { document.getElementById("preboot")?.remove(); } catch { /* noop */ }

// ---- CLOUD profile (paid account): /api/config exposes `cloud_profile` (= ZAELAR_USER_ID set by the
// provisioner). In cloud the header is reduced to PROFILE + theme (TopBar gates it); in self-host it is false and nothing changes.
// RETRY (2026-08-13): during a cold START of the account Machine, /api/config returns 503 until
// FastAPI finishes starting. With one failed attempt, cloud_profile stayed false FOREVER and the header
// rendered the LOCAL menu in the cloud. Retry until it responds — the actual state prevails. ----
(async () => {
  for (let i = 0; i < 45; i++) {
    try { const cfg = await api.getConfig(); if (cfg) { store.setCloudProfile(!!cfg.cloud_profile); return; } }
    catch { /* 503 while the Machine starts: retry */ }
    await new Promise((r) => setTimeout(r, 2000));
  }
})();

// ---- ENERGY BALANCE: seeds the top bar's STACK (EnergyGauge.js). Afterwards it lives off SSE (`kind:"energy"`),
// which brings the new balance with each spend — so it drops live without any polling. Same retry as above, for the
// same reason: on a cold Machine startup the endpoint is not available yet. ----
(async () => {
  for (let i = 0; i < 45; i++) {
    try {
      const r = await fetch("/api/energy", { cache: "no-store" });
      if (r.ok) { store.setEnergy(await r.json()); return; }
    } catch { /* the Machine is still starting: retry */ }
    await new Promise((r) => setTimeout(r, 2000));
  }
})();

// ---- V2-101: first-run language onboarding — the SECOND blocking veil, right after the boot veil (voice must
// be connected for zaelar to hear the answer). Checked ONCE bootReady() first flips true; GET /api/i18n/state's
// `chosen` field says whether ANY language has ever been explicitly picked — false only on a brand-new install
// (or one that wiped config/settings.json on reset). A returning operator, or one who already answered, never
// sees this: the effect below fires at most once (`_langOnboardChecked` guard). ----
let _langOnboardChecked = false;
createEffect(() => {
  if (_langOnboardChecked || !store.bootReady()) return;
  _langOnboardChecked = true;
  fetch("/api/i18n/state", { cache: "no-store" }).then(r => r.json()).then(s => {
    if (s && s.chosen === false) store.setLangOnboardOpen(true);
  }).catch(() => {});
});

// ---- widget desktop (independent canvas / window manager) ----
const desktop = new Desktop($("#wstage"));
window.__zaelarDesktop = desktop;   // the SSE/session bridge reaches the desktop through this
// V2-092: the agent state reaches EVERY widget through its `ctx.running`. Reactive, so a ⏻ (here or in another
// tab, via SSE) sees it instantly and a widget playing something does not start on a stopped agent.
createEffect(() => desktop.setRunning(!store.powerOff()));

// ---- server events → desktop, FROM STARTUP and without depending on voice (2026-08-09) ----
// `openSSE` was called ONLY inside `session.start()` (services/session.js), that is, after obtaining the
// microphone and setting up WebRTC. Consequence: without voice NO widget event arrived, and "without voice" includes
// real, everyday cases — the operator with ⏻ off (store.powerOff, which the app has intentionally used this way since
// chat and voice became independent), a browser that denies the microphone, or any startup where voice has not
// come up yet. In all of them an open widget remained FROZEN in the snapshot of its first render: a worker
// could be pushing results one by one and the screen would not know. Exactly the opposite of what this surface is
// meant to provide —watching the report fill in live— and with no symptom to reveal it.
// The observability bus (services/debugbus.js) solved this the same way: its own subscriber to /events,
// independent of the session. `openSSE` is idempotent, so the `session.start()` call remains without
// opening a second connection.
openSSE(desktop);

// ---- always-on render loop (orb = zaelar's voice, viz = the person's voice) ----
session.startVisuals({ orbCanvas: $("#orb"), vizCanvas: $("#viz") });

// ---- ALWAYS-ON voice: the session auto-connects. Browsers may require a user gesture for the mic/audio, so we
// also (re)connect on ANY pointer interaction whenever the session isn't up. Idempotent (only starts when stopped)
// and re-arms after Reset. ONE exception (V2-039 «ojo»): the ⏻ power icon on the orb's upper lid — an EXPLICIT,
// persisted operator off (store.powerOff) that this auto-connect must respect, or the very click on ⏻ would
// re-arm the session it just stopped. To just silence zaelar keep using 🔊 (mute; agent keeps running).
function ensureVoice() { if (store.powerOff()) return; if (!store.started() && !store.starting()) session.start().catch(() => {}); }
// Real bug 2026-07-24 (operator report: "does not progress from Starting to zaelar…"): with ⏻ off from a previous
// session (persisted in localStorage), `ensureVoice()` NEVER calls `session.start()` — and `start()` is the
// only place that arms the safety timer and calls `_unblockBoot()`. Without it, `store.bootReady()` stays
// `false` FOREVER and BootOverlay remains stuck on the first label ("Starting zaelar…")
// on every page load/reload — there is nothing to start (voice intentionally off), so there is nothing
// to wait for either: remove the veil NOW instead of pretending a startup will ever come.
if (store.powerOff()) store.setBootReady(true);
ensureVoice();
window.addEventListener("pointerdown", ensureVoice);

// ---- V2-092: RECONCILE with the SERVER truth (`nucleo/runstate.py`) --------------------------------------
// ⏻ lived only in localStorage, which is per-browser and per-origin and cannot be queried by the backend.
// Real consequence (operator, 2026-08-13): with the agent stopped, RELOADING the page started the video again.
// The server now stores whether the agent is stopped and reconciliation happens here, in the SAFE direction:
//   · server STOPPED → obey: shut down here too and tear down the session if it had already started (seeding is async,
//     so `ensureVoice()` above may have started it before this response arrives).
//   · server RUNNING with ⏻ off HERE → propagate our intent to the server (POST /api/run/stop) instead
//     of starting on our own. Never the reverse: a startup the operator did not request is worse than stale state,
//     and this also covers migration (⏻ off before the server knew about it).
//
// And a third rule, learned from a failure the operator captured (2026-08-14): this reply is a SNAPSHOT of the
// moment it was requested, not of the moment it arrives. On a machine waking from cold that takes seconds, and the
// operator — who is staring at the screen precisely because it will not start — presses ⏻ inside that window. The
// snapshot landed afterwards, said "stopped" (true BEFORE the click), and tore down the session they had just asked
// for: the mic was already open, `stop()` closed it mid-startup and `start()` blew up with an error that mentions
// neither ⏻ nor startup. The SLOWEST message won instead of the NEWEST one.
//   → Stamp the instant BEFORE asking, and drop the reply if the operator commanded anything meanwhile. Their
//     command already travels to the server by its own path (`api.runStart()` in the ⏻), so nothing is lost.
(async () => {
  try {
    const askedAt = Date.now();
    const r = await api.runState();
    if (!r || typeof r.running !== "boolean") return;
    if (store.powerCmdAt() > askedAt) return;   // the operator commanded LATER: this snapshot is history
    if (!r.running) { store.setPowerOff(true); store.setMicMuted(true); store.setBotMuted(true); }
    else if (store.powerOff()) api.runStop();
  } catch { /* the server is not responding yet: local state prevails, as it is already applied */ }
})();

// STOPPED ⇒ NO VOICE SESSION, regardless of where the command comes from. ⏻ already calls `session.stop()` on its own click,
// but since V2-092 the state can arrive from OUTSIDE this tab: from the seeding above (the server says the
// agent was stopped) or the SSE `run` event (another window pressed ⏻). Without this, that tab would render
// off with the microphone open — the state lying again. Idempotent: stop only if something was running.
createEffect(() => {
  if (!store.powerOff()) return;
  store.setBootReady(true);                       // nothing to wait for: no startup is in progress and none will be
  if (store.started() || store.starting()) { try { session.stop(); } catch (_) {} }
});

// AND THE OPPOSITE DIRECTION (2026-08-31). The one above had covered only SHUTDOWN since V2-092: if
// `powerOff` was lifted from OUTSIDE this tab —the SSE `run`/start event (another window pressed ⏻, or the
// server itself started), or the `session-lk.js` guard undoing a false shutdown— nobody called
// `session.start()` again. Voice waited for the NEXT `pointerdown`, the other path to `ensureVoice()`: ⏻ stayed
// amber until the operator touched anything else, and RELOADING the page fixed it instantly
// (startup seeding does call `ensureVoice()`). A state fixed only by reloading is exactly the state that lies.
// `ensureVoice()` is idempotent: if it is already running, it does nothing.
createEffect(() => {
  if (store.powerOff()) return;
  ensureVoice();
});

// ---- CLIENT STATE → observability (2026-08-10) ----------------------------------------------------------
// Until now the log contained only the operator's INTENT (`orb:power` when pressing ⏻), never REALITY: an agent
// that had crashed but was rendered alive —the failure that cost an entire session— was invisible from the server. `agentState()`
// is the single source of truth (off/starting/live/stalled, see store.js), so its TRANSITION is the missing event:
// `stalled` with `prev:"live"` means «it crashed while running»; with `prev:"starting"` it means «it never came up». Two
// very different readings that previously had to be guessed.
//
// A `createEffect` over a DERIVED signal reruns when any of its dependencies changes
// (`powerOff`/`started`/`starting`/`bootReady`), and several of those combinations produce the SAME state — hence the
// guard: emit on the actual change, not on every reevaluation. That is the rule for these events: state, not activity.
let _prevAgentState = null;
createEffect(() => {
  const s = store.agentState();
  if (s === _prevAgentState) return;
  const prev = _prevAgentState;
  _prevAgentState = s;
  api.uiState("agent:state", { state: s, prev: prev || "none" });
});

// A background tab does NOT run `requestAnimationFrame`, and the visualizer loop and several frontend guards depend
// on rAF. Without this line, «it froze» and «you were in another application» are indistinguishable in the log —
// and that confusion has already cost us an entire diagnosis.
try {
  document.addEventListener("visibilitychange", () => {
    api.uiState("tab:visibility", { state: document.hidden ? "hidden" : "visible" });
  });
} catch (_) {}

// ---- manual control surface: window.zaelar.show('search','tiempo en Soria') · .close() · .gate(true) · .orb('friendly') ----
window.zaelar = {
  show: (id, q = "") => desktop && desktop.show(id, { q }),
  close: (id) => desktop && (id ? desktop.close(id) : desktop.closeAll()),
  gate: (on) => session.setGate(on),
  retrain: () => session.retrain(),
  orb: (s) => session.setOrb(s),
  vault: (mode = "manage") => store.openVault(mode),   // 🔐 secrets vault (V2-060): create/unlock/manage
  panel: (tab = "chat") => { store.setChatTab(["chat", "procesos", "crons"].includes(tab) ? tab : "chat"); store.setChatOpen(true); },  // V2-079: opens the native panel (chat/procesos/crons)
};

// ---- files: paste an image / drop a file → lands in the central memory's EPISODIC layer (V2-003); the brain
// gets a [SISTEMA] note (voice/brain_notes.py) and can recall it once asked. See memory/server_api.py.
async function uploadFile(file, source) {
  try {
    const fd = new FormData();
    fd.append("file", file, file.name || "archivo");
    fd.append("source", source);
    const res = await fetch("/api/files/upload", { method: "POST", body: fd });
    const d = await res.json();
    if (!res.ok) throw new Error(d && d.detail || "upload failed");
    store.pushChat({ role: "sys", text: source === "paste" ? t("main.image_sent", { name: d.name }) : t("main.file_added", { name: d.name }) });
  } catch (_) {
    store.pushChat({ role: "sys", text: t("main.upload_failed") });
  }
}

// ---- Ctrl/Cmd+V anywhere → feed the clipboard text (or a pasted image) to the agent (even if the chat wall is
// hidden). Pasting while focused in a real input/textarea (the chat box, settings fields) keeps native behaviour,
// EXCEPT for images — a screenshot pasted into any input still lands in the files inbox, since inputs can't hold it.
window.addEventListener("paste", (e) => {
  const cd = e.clipboardData || window.clipboardData;
  const items = (cd && cd.items) || [];
  for (const item of items) {
    if (item.kind === "file" && /^image\//.test(item.type)) {
      const file = item.getAsFile();
      if (file) { e.preventDefault(); uploadFile(file, "paste"); }
    }
  }

  const t = e.target;
  if (t && (t.isContentEditable || /^(input|textarea|select)$/i.test(t.tagName || ""))) return;
  const text = (cd && cd.getData("text")) || "";
  if (!text.trim()) return;
  e.preventDefault();
  submitChat(text);   // sends to the agent + records it in the chat wall (no need to open it)
});

// ---- drag & drop anywhere → upload to the files inbox instead of the browser opening the file ----
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => {
  const files = (e.dataTransfer && e.dataTransfer.files) || [];
  if (!files.length) return;
  e.preventDefault();
  for (const file of files) uploadFile(file, "drop");
});

// system-status poller: keeps the ◉ icon's color/blink live even with the panel closed
startStatusPolling();

// load the voice catalog (tap the orb to cycle), then honor /?widget=<id> for manual opening
session.loadVoices();
(function () { const w = new URLSearchParams(location.search).get("widget"); if (w) setTimeout(() => desktop && desktop.show(w), 700); })();
