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

// SUPERFICIES NATIVAS del frontend (widgets de SISTEMA, intocables): la LISTA CANÓNICA ÚNICA vive en
// core/system-surfaces.js — main.js las MONTA desde ahí (sin lista duplicada). `submitChat` es el único símbolo
// de un componente que main.js usa aparte de montar (el handler de pegar del portapapeles).
import { submitChat } from "./components/ChatWall.js?v=5";
import { SYSTEM_SURFACES } from "./core/system-surfaces.js?v=1";
import * as api from "./services/api.js?v=2";

import { Desktop } from "./widgets/desktop.js?v=3";

// ---- theme (dark/light) — apply before mounting anything, so nothing flashes the wrong palette ----
initTheme();
// ---- active UI language (V2-089): the store seeded instantly from the localStorage mirror; reconcile with the
// backend's active language (ZAELAR_LANGUAGE). t() is reactive, so any correction re-renders the UI in place. ----
initI18n();

// ---- #desk = EL ESCRITORIO como UNA sola unidad (V2-062) — la "columna central" del layout de 3 columnas.
// Todo el escritorio (fondo, widgets, cámara, orbe, TopBar, estado) vive DENTRO. Cuando el chat se acopla a un
// borde, #desk se encoge de ese lado (CSS: left/right = --chatdock-*, con `transform` que lo hace bloque contenedor)
// → TODOS sus hijos position:fixed se recolocan relativos a #desk y se desplazan JUNTOS, incluidos los que tienen
// posición inline arrastrada (orbe, cámara) que el offset por-elemento NO podía mover. Los overlays/paneles/modales
// y el propio chat se montan FUERA de #desk (a nivel de body), por encima. ----
const desk = mount(h("div", { id: "desk" }));

// ---- static scaffold (backdrop, widget stage, bot audio sink) ----
mount(h("div", { class: "canvas" }), desk);
// superficies de sistema de FASE scaffold (hoy: el panal de actividad) — van justo encima de .canvas y DEBAJO del
// widget stage (V2-039: todo pinta por encima del panal). Se montan desde la lista canónica.
for (const s of SYSTEM_SURFACES.filter(s => s.phase === "scaffold")) mount(s.comp(), desk);
mount(h("div", { class: "wstage", id: "wstage" }), desk);   // widgets pop onto the canvas here
const botAudio = mount(h("audio", { id: "botaudio", autoplay: true }));
session.attachBotAudio(botAudio);
// Vinculación reactiva icono↔audio: el <audio> SIEMPRE refleja botMuted() (lo mismo que pinta el icono 🔊 del
// cuenco) — el switch on/off aplica al instante y nunca queda "icono silenciado pero suena" (bug de arranque V2-043).
createEffect(() => { try { botAudio.muted = store.botMuted(); } catch (_) {} });

// ---- SUPERFICIES DE SISTEMA (nativas, intocables) — montadas desde la LISTA CANÓNICA ÚNICA
// (core/system-surfaces.js), en su orden de apilado. chrome del escritorio → #desk (se desplaza al acoplar el
// chat); paneles/overlays/modales/chat/banners → body (por encima). Añadir una superficie nativa = añadirla a
// esa lista; aquí no se toca nada. Todo lo DEMÁS que aparece en pantalla son widgets de USUARIO (catálogo
// widgets/<id>/, aunque se distribuyan de serie) — variables, creados por/para el usuario, como los conectores. ----
for (const s of SYSTEM_SURFACES.filter(s => s.phase === "overlay")) {
  mount(s.comp(), s.target === "desk" ? desk : undefined);
}

// ---- primer arranque: si la config no está validada, abre el wizard ANTES de nada (config gestionada por la UI) ----
api.wizardState().then(s => { if (s && s.first_run) store.setWizardOpen(true); }).catch(() => {});

// El splash inline (#preboot en index.html) ya cumplió su papel (loader desde el PRIMER byte); los módulos han
// cargado y el BootOverlay (velo de neuronas) toma el relevo → quítalo para no solapar dos loaders. Si main.js
// hubiera fallado al cargar, #preboot se queda (mejor un loader que una pantalla negra).
try { document.getElementById("preboot")?.remove(); } catch { /* noop */ }

// ---- perfil CLOUD (cuenta de pago): /api/config expone `cloud_profile` (= ZAELAR_USER_ID puesto por el
// provisioner). En cloud el header se reduce a PERFIL + tema (TopBar lo gatea); en self-host es false y nada cambia.
// REINTENTO (2026-08-13): en el ARRANQUE EN FRÍO de la Machine de cuenta, /api/config devuelve 503 hasta que el
// FastAPI termina de subir. Con un solo intento fallido, cloud_profile se quedaba en false PARA SIEMPRE y el header
// pintaba el menú LOCAL en la nube. Se reintenta hasta que responde — el estado real manda. ----
(async () => {
  for (let i = 0; i < 45; i++) {
    try { const cfg = await api.getConfig(); if (cfg) { store.setCloudProfile(!!cfg.cloud_profile); return; } }
    catch { /* 503 mientras la Machine arranca: reintentar */ }
    await new Promise((r) => setTimeout(r, 2000));
  }
})();

// ---- SALDO DE ENERGY: siembra la PILA de la barra superior (EnergyGauge.js). Después vive del SSE (`kind:"energy"`),
// que trae el saldo nuevo con cada gasto — así baja en vivo sin ningún polling. Mismo reintento que arriba, por la
// misma razón: en el arranque en frío de la Machine el endpoint aún no está. ----
(async () => {
  for (let i = 0; i < 45; i++) {
    try {
      const r = await fetch("/api/energy", { cache: "no-store" });
      if (r.ok) { store.setEnergy(await r.json()); return; }
    } catch { /* la Machine sigue subiendo: reintentar */ }
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
// V2-092: el estado del agente llega a TODO widget por su `ctx.running`. Reactivo, así que un ⏻ (aquí o en otra
// pestaña, vía SSE) lo ve al instante y un widget que reproduce algo no arranca solo sobre un agente parado.
createEffect(() => desktop.setRunning(!store.powerOff()));

// ---- eventos del server → escritorio, DESDE EL ARRANQUE y sin depender de la voz (2026-08-09) ----
// `openSSE` se llamaba SOLO dentro de `session.start()` (services/session.js), o sea después de conseguir el
// micrófono y montar el WebRTC. Consecuencia: sin voz no llegaba NINGÚN evento de widget, y "sin voz" son casos
// reales y cotidianos — el operador con ⏻ apagado (store.powerOff, que ya usa la app a propósito así desde que
// chat y voz son independientes), un navegador que niega el micro, o cualquier arranque en el que la voz aún no
// ha subido. En todos ellos un widget abierto se quedaba CONGELADO en la foto de su primer render: un worker
// podía estar empujando resultados uno a uno y la pantalla no se enteraba. Justo lo contrario de lo que se pide
// de esta superficie —ver llenarse el informe en vivo— y sin ningún síntoma que lo delatara.
// El bus de observabilidad (services/debugbus.js) ya resolvió esto igual: suscriptor propio a /events,
// independiente de la sesión. `openSSE` es idempotente, así que la llamada de `session.start()` sigue ahí sin
// abrir una segunda conexión.
openSSE(desktop);

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

// ---- V2-092: RECONCILIAR con la verdad del SERVIDOR (`nucleo/runstate.py`) --------------------------------------
// El ⏻ vivía solo en el localStorage, que es per-navegador y per-origen y al que el backend no puede preguntar.
// Consecuencia real (operador, 2026-08-13): con el agente parado, RECARGAR la página volvía a arrancar el vídeo.
// Ahora el servidor guarda si el agente está parado y aquí se reconcilia, en la dirección SEGURA:
//   · servidor PARADO → obedecer: apagar aquí también y tumbar la sesión si ya había subido (la siembra es async,
//     así que `ensureVoice()` de arriba puede haberla arrancado antes de que llegue esta respuesta).
//   · servidor EN MARCHA con el ⏻ apagado AQUÍ → propagar nuestra intención al servidor (POST /api/run/stop) en vez
//     de encender solos. Nunca al revés: un arranque que el operador no pidió es peor que un estado desactualizado,
//     y esto cubre además la migración (un ⏻ apagado antes de que el servidor supiera de esto).
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
  } catch { /* el servidor aún no responde: manda el estado local, que ya está aplicado */ }
})();

// PARADO ⇒ SIN SESIÓN DE VOZ, venga la orden de donde venga. El ⏻ ya llama a `session.stop()` en su propio click,
// pero desde V2-092 el estado puede llegar de FUERA de esta pestaña: de la siembra de arriba (el servidor dice que
// el agente estaba parado) o del evento SSE `run` (otra ventana pulsó ⏻). Sin esto, esa pestaña se pintaría
// apagada con el micro abierto — el estado que miente, otra vez. Idempotente: paramos solo si había algo en pie.
createEffect(() => {
  if (!store.powerOff()) return;
  store.setBootReady(true);                       // nada que esperar: no hay arranque en curso ni lo habrá
  if (store.started() || store.starting()) { try { session.stop(); } catch (_) {} }
});

// ---- ESTADO DEL CLIENTE → observabilidad (2026-08-10) ----------------------------------------------------------
// Hasta ahora el log solo tenía la INTENCIÓN del operador (`orb:power` al pulsar ⏻), nunca la REALIDAD: un agente
// caído que se pintaba vivo —el fallo que costó una sesión entera— era invisible desde el servidor. `agentState()`
// es la verdad única (off/starting/live/stalled, ver store.js), así que su TRANSICIÓN es el evento que faltaba:
// `stalled` con `prev:"live"` es «se ha caído en marcha»; con `prev:"starting"` es «no llegó a subir». Dos lecturas
// muy distintas que antes había que adivinar.
//
// Un `createEffect` sobre una señal DERIVADA se re-ejecuta cuando cambia cualquiera de sus dependencias
// (`powerOff`/`started`/`starting`/`bootReady`), y varias de esas combinaciones dan el MISMO estado — de ahí el
// guarda: se emite en el cambio real, no en cada re-evaluación. Es la regla de estos eventos: estado, no actividad.
let _prevAgentState = null;
createEffect(() => {
  const s = store.agentState();
  if (s === _prevAgentState) return;
  const prev = _prevAgentState;
  _prevAgentState = s;
  api.uiState("agent:state", { state: s, prev: prev || "none" });
});

// La pestaña en segundo plano NO ejecuta `requestAnimationFrame`, y de rAF dependen el bucle del visualizador y
// varios guardas del frontend. Sin esta línea, «se quedó congelado» y «estabas en otra aplicación» son
// indistinguibles en el log — y esa confusión ya nos costó un diagnóstico entero.
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
