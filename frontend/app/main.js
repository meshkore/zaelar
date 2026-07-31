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
import * as store from "./core/store.js?v=2";
import { startStatusPolling } from "./services/status.js?v=2";
import { initTheme } from "./services/theme.js?v=2";

import { Alert } from "./components/Alert.js?v=2";
import { BootOverlay } from "./components/BootOverlay.js?v=2";
import { CameraUnit } from "./components/CameraUnit.js?v=2";
import { ChatWall, submitChat } from "./components/ChatWall.js?v=5";
import { StatusPanel } from "./components/StatusPanel.js?v=2";
import { TopBar } from "./components/TopBar.js?v=3";
import { ConfigPanel } from "./components/ConfigPanel.js?v=1";
import { BenchmarksPanel } from "./components/BenchmarksPanel.js?v=1";
import { Orb } from "./components/Orb.js?v=3";
import { ActivityStrip } from "./components/ActivityStrip.js?v=2";
import { ConnStatus } from "./components/ConnStatus.js?v=2";
import { DebugPanel } from "./components/DebugPanel.js?v=4";
import { MemoryMap } from "./components/MemoryMap.js?v=2";
import { WizardModal } from "./components/WizardModal.js?v=1";
import { VaultModal } from "./components/VaultModal.js?v=1";
import * as api from "./services/api.js?v=2";

import { Desktop } from "./widgets/desktop.js?v=3";

// ---- theme (dark/light) — apply before mounting anything, so nothing flashes the wrong palette ----
initTheme();

// ---- #desk = EL ESCRITORIO como UNA sola unidad (V2-062) — la "columna central" del layout de 3 columnas.
// Todo el escritorio (fondo, widgets, cámara, orbe, TopBar, estado) vive DENTRO. Cuando el chat se acopla a un
// borde, #desk se encoge de ese lado (CSS: left/right = --chatdock-*, con `transform` que lo hace bloque contenedor)
// → TODOS sus hijos position:fixed se recolocan relativos a #desk y se desplazan JUNTOS, incluidos los que tienen
// posición inline arrastrada (orbe, cámara) que el offset por-elemento NO podía mover. Los overlays/paneles/modales
// y el propio chat se montan FUERA de #desk (a nivel de body), por encima. ----
const desk = mount(h("div", { id: "desk" }));

// ---- static scaffold (backdrop, widget stage, bot audio sink) ----
mount(h("div", { class: "canvas" }), desk);
mount(ActivityStrip(), desk);   // background-activity HONEYCOMB: right above .canvas so EVERYTHING paints over it (V2-039)
mount(h("div", { class: "wstage", id: "wstage" }), desk);   // widgets pop onto the canvas here
const botAudio = mount(h("audio", { id: "botaudio", autoplay: true }));
session.attachBotAudio(botAudio);
// Vinculación reactiva icono↔audio: el <audio> SIEMPRE refleja botMuted() (lo mismo que pinta el icono 🔊 del
// cuenco) — el switch on/off aplica al instante y nunca queda "icono silenciado pero suena" (bug de arranque V2-043).
createEffect(() => { try { botAudio.muted = store.botMuted(); } catch (_) {} });

// ---- components: chrome del ESCRITORIO → #desk (se desplaza); overlays/paneles/chat → body (por encima) ----
mount(Alert());
mount(BootOverlay());
mount(CameraUnit(), desk);
mount(ChatWall());     // la columna acoplable — FUERA de #desk (es quien lo empuja). V2-079: incluye las pestañas
//                        Chat/Procesos/Crons (el antiguo CronPanel suelto se fundió aquí, en la 3ª pestaña).
mount(StatusPanel());
mount(TopBar(), desk);
mount(ConfigPanel());  // ⚙ área de configuración full-screen: API/modelo por pieza + voz + saldos (V2-043)
mount(BenchmarksPanel());  // "¿por qué estos modelos?" — solo informativo, abierta desde el cerebro rápido (V2-077)
mount(Orb(), desk);
mount(ConnStatus(), desk);
mount(DebugPanel());   // resizable observability side-column (◷ in the TopBar); shrinks the canvas when open
mount(MemoryMap());    // 🧠 memory map overlay (state + short/long-term + concept graph), toggled from the orb bowl
mount(WizardModal());  // 🧭 wizard de primer arranque (perfil local/cloud + detector + credenciales, V2-040)
mount(VaultModal());   // 🔐 bóveda de secretos: crear/desbloquear (passphrase o passkey), mostrar valor (V2-060)

// ---- primer arranque: si la config no está validada, abre el wizard ANTES de nada (config gestionada por la UI) ----
api.wizardState().then(s => { if (s && s.first_run) store.setWizardOpen(true); }).catch(() => {});

// ---- widget desktop (independent canvas / window manager) ----
const desktop = new Desktop($("#wstage"));
window.__zaelarDesktop = desktop;   // the SSE/session bridge reaches the desktop through this

// ---- always-on render loop (orb = zaelar's voice, viz = the person's voice) ----
session.startVisuals({ orbCanvas: $("#orb"), vizCanvas: $("#viz") });

// ---- ALWAYS-ON voice: the session auto-connects. Browsers may require a user gesture for the mic/audio, so we
// also (re)connect on ANY pointer interaction whenever the session isn't up. Idempotent (only starts when stopped)
// and re-arms after Reset. ONE exception (V2-039 «ojo»): the ⏻ power icon on the orb's upper lid — an EXPLICIT,
// persisted operator off (store.powerOff) that this auto-connect must respect, or the very click on ⏻ would
// re-arm the session it just stopped. To just silence zaelar keep using 🔊 (mute; agent keeps running).
function ensureVoice() { if (store.powerOff()) return; if (!store.started() && !store.starting()) session.start().catch(() => {}); }
// Bug real 2026-07-24 (reporte del operador: "no pasa de Encendiendo a zaelar…"): con ⏻ apagado desde una sesión
// anterior (persistido en localStorage), `ensureVoice()` no llama NUNCA a `session.start()` — y es `start()` el
// único sitio que arma el temporizador de seguridad y llama a `_unblockBoot()`. Sin él, `store.bootReady()` se
// queda en `false` PARA SIEMPRE y el BootOverlay se queda clavado en el primer rótulo ("Encendiendo a zaelar…")
// en cada carga/recarga de la página — no hay nada que arrancar (voz apagada a propósito), así que no hay nada
// que esperar tampoco: quita el velo YA en vez de fingir un arranque que nunca vendrá.
if (store.powerOff()) store.setBootReady(true);
ensureVoice();
window.addEventListener("pointerdown", ensureVoice);

// ---- manual control surface: window.zaelar.show('search','tiempo en Soria') · .close() · .gate(true) · .orb('friendly') ----
window.zaelar = {
  show: (id, q = "") => desktop && desktop.show(id, { q }),
  close: (id) => desktop && (id ? desktop.close(id) : desktop.closeAll()),
  gate: (on) => session.setGate(on),
  retrain: () => session.retrain(),
  orb: (s) => session.setOrb(s),
  vault: (mode = "manage") => store.openVault(mode),   // 🔐 bóveda de secretos (V2-060): crear/desbloquear/gestionar
  panel: (tab = "chat") => { store.setChatTab(["chat", "procesos", "crons"].includes(tab) ? tab : "chat"); store.setChatOpen(true); },  // V2-079: abre el panel nativo (chat/procesos/crons)
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
    store.pushChat({ role: "sys", text: (source === "paste" ? "📎 imagen enviada: " : "📁 archivo añadido: ") + d.name });
  } catch (_) {
    store.pushChat({ role: "sys", text: "⚠️ no se pudo subir el archivo" });
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
