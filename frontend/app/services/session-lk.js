// ============================================================================
// session-lk.js — the voice session ENGINE on LiveKit (INI-012).
//
// Drop-in replacement for session.js: SAME export surface (components import it
// unchanged), but the transport is a LiveKit Room instead of a raw RTCPeer-
// Connection. LiveKit owns streaming, turn-taking, VAD and barge-in server-side,
// so the browser no longer runs Silero VAD or Web-Speech STT.
//
// What stays identical:
//   • The reactive store contract (same signals: started/conn/latency/micLevel/…).
//   • SSE (openSSE) for EVERY backend→UI event (widgets, bot_speech, transcript,
//     alerts) — the agent worker is EMBEDDED in the web-server process, so
//     voice.observer.emit reaches the same /events stream as before.
//   • The mic analyser / orb visualiser: we still getUserMedia the mic locally
//     (for the analyser) AND publish that same track to LiveKit.
//   • Camera stays a LOCAL preview (not published), exactly as before.
//
// Loaded instead of session.js when the backend runs the LiveKit engine
// (main.js picks the engine from /api/livekit). See INI-012.
// ============================================================================
import { Room, RoomEvent, LocalAudioTrack, ConnectionState } from "../../vendor/livekit-client.esm.js";
import * as store from "../core/store.js?v=2";
import * as audio from "./audio.js?v=2";
import * as api from "./api.js?v=2";
import { openSSE } from "./sse.js?v=4";
import { clearDebugBuffer } from "./debugbus.js?v=2";
import { startVisualizer } from "./visualizer.js?v=2";
import { t } from "../core/i18n.js?v=1";

let room = null, stream = null, videoEl = null, botAudioEl = null;
let started = false, starting = false;

// SESSION GENERATION. Bumped by every `stop()`, invalidating any `start()` still in flight.
//
// Born from a real failure (operator, 2026-08-14): `start()` has SIX `await`s between asking for the mic and using
// it (permission, device enumeration, camera, token, connect), and during that stretch the session can be torn
// down from outside — ⏻ in another tab, the SSE `run` event, the server reconciliation, the energy fuse. `stop()`
// sets `stream = null`, so the `start()` still running reached `audio.initMic(stream)` holding `null` and blew up
// with "parameter 1 is not of type 'MediaStream'": an error naming neither the stop nor ⏻, and which on top of
// that left the JUST-OPENED mic running (`stop()` had already gone by, with `stream` still empty).
//
// The counter is the cheap way for a `start()` to know it is no longer the current one. `started/starting` cannot
// do it: `stop()` sets them false, which is indistinguishable from "I have not finished coming up yet".
let _gen = 0;
let micDeviceId = localStorage.getItem("zaelar_mic") || null;
const audit = { silent: false };

// ── Modo de CAPTURA del micro (acondicionamiento de la señal ANTES del STT) ──────────────────────────────────
// El transcriptor (Whisper) no es el cuello de botella en un sitio ruidoso: lo que falla es la SEÑAL que le
// llega. Chrome aplica su propio APM (echoCancellation/noiseSuppression) al pedir getUserMedia — su NS clásico es
// débil con ruido no-estacionario (música) y, en macOS, PELEA con el "Aislamiento de voz" del sistema (que es ML,
// mucho más fuerte, el mismo tipo de limpieza que hace SuperWhisper). Tres modos:
//   • isolate → SOLO echoCancellation. Enciende el audio-unit de voice-processing de macOS (donde engancha el
//               Aislamiento de voz del sistema) SIN el NS de Chrome encima → deja que macOS mande. DEFAULT en Mac.
//   • full    → APM completo de Chrome (EC+NS+AGC). Mejor en Windows/Linux sin aislamiento a nivel de SO.
//   • raw     → sin ningún procesado (diagnóstico / micro externo con su propio DSP).
// OJO: la constraint `voiceIsolation` es de Safari/WebKit; Chrome la ignora en silencio → NO la usamos (era un
// no-op que daba falsa sensación de aislamiento). En Chrome el aislamiento de voz se activa desde el SO
// (Centro de control → Micrófono → Aislamiento de voz), no por getUserMedia.
const _MIC_MODES = {
  isolate: { echoCancellation: true,  noiseSuppression: false, autoGainControl: false },
  full:    { echoCancellation: true,  noiseSuppression: true,  autoGainControl: true  },
  raw:     { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
};
const _isMac = /Mac|iP(hone|ad|od)/.test(navigator.platform || navigator.userAgent || "");
function micMode() {
  const sp = new URLSearchParams(location.search);
  if (sp.get("raw") === "1") return "raw";
  if (sp.get("aec") === "1" || sp.get("isolate") === "1") return "isolate";
  if (sp.get("full") === "1") return "full";
  const saved = localStorage.getItem("zaelar_micmode");
  if (saved && _MIC_MODES[saved]) return saved;
  return _isMac ? "isolate" : "full";   // Mac: deja mandar al Aislamiento de voz del SO
}

// ---- UNA SOLA SESIÓN DE VOZ VIVA POR MÁQUINA (2026-07-12): evita dos micros abiertos (dos pestañas/navegadores)
// que vuelven loco el pipeline de eventos. El server es el árbitro (localhost = mismo ordenador). `SID` es único
// POR PESTAÑA (sessionStorage: sobrevive a un reload de ESTA pestaña, distinto en otra). Si al arrancar el lock lo
// tiene otra pestaña viva, NO abrimos el micro: mostramos el aviso y reintentamos solos cada 3s (cuando la otra se
// cierre, el lock se libera y esta pestaña entra sola). Mientras vivimos, latimos cada 4s para conservar el lock. ----
const SID = (() => {
  let s = sessionStorage.getItem("zaelar_sid");
  if (!s) { s = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(36).slice(2)); sessionStorage.setItem("zaelar_sid", s); }
  return s;
})();
let _hb = null, _blockedRetry = null;
function _startHeartbeat() {
  if (_hb) return;
  _hb = setInterval(() => {
    api.sessionHeartbeat(SID).then((r) => {
      if (r && r.ok === false && started) {   // perdimos la carrera (otra pestaña viva) → cede el paso, no dos micros
        console.warn("session lock perdido — otra sesión tomó el control; cierro esta.");
        stop();
        store.setMicBlocked({ show: true, msg: t("voice.session_active_other_tab") });
      }
    });
  }, 4000);
}
function _stopHeartbeat() { if (_hb) { clearInterval(_hb); _hb = null; } }
// Soltar el lock al cerrar la pestaña (sendBeacon sobrevive al unload) → otra pestaña puede entrar al instante.
try { window.addEventListener("pagehide", () => { api.sessionRelease(SID); api.obsSessionEnd("tab_closed"); }); } catch (_) {}

// ---- boot overlay: only the VERY FIRST boot blocks the UI; later reconnects (mic swap, auto-reconnect, voice
// picker) never re-lock it. A safety timeout unblocks even if the agent's "ready" signal never arrives — a
// stuck boot must never lock the UI out for good. ----
let _everBooted = false, _bootTimer = null;
function _unblockBoot() {
  clearTimeout(_bootTimer); _bootTimer = null;
  _everBooted = true;
  store.setBootPhase("listo");   // last cluster lights up → the splash implodes into the orb (boot-anim.js)
  store.setBootReady(true);
}
// Advance the boot phase ONLY during the very first boot (later reconnects never touch the splash). Ignores
// out-of-order/unknown phases so a late backend milestone can't rewind the animation.
function _bootPhase(p) {
  if (_everBooted) return;
  const cur = store.BOOT_PHASES.indexOf(store.bootPhase());
  const nxt = store.BOOT_PHASES.indexOf(p);
  if (nxt > cur) store.setBootPhase(p);
}

// injected by components/main on mount (same as session.js)
export function attachVideo(el) { videoEl = el; }
export function attachBotAudio(el) {
  botAudioEl = el;
  // PARIDAD icono↔audio — INVARIANTE AUTO-CORRECTIVA (bug de hidratación 2026-07-17): el `attachToElement` del
  // vendor LiveKit hace `element.muted = false` en CADA attach — incluidos los RE-ATTACH INTERNOS al reemplazar el
  // mediaStreamTrack (track nuevo del agente tras el arranque / reconexión), que corren SIN pasar por nuestro
  // TrackSubscribed y SIN disparar 'playing' (reutiliza el mismo MediaStream → no hay reload). Resultado: icono
  // "silenciado" (localStorage) pero la voz SONANDO tras un refresh. Como cualquier cambio de muted/volume dispara
  // 'volumechange', re-asertamos ahí el estado del signal (guard anti-recursión: solo escribe si difiere) + cinturón
  // de volume=0 (el vendor nunca toca volume en este path) + HIDRATACIÓN inmediata del estado persistido al montar.
  const enforce = () => {
    const want = store.botMuted();
    if (el.muted !== want) el.muted = want;
    if (want && el.volume !== 0) el.volume = 0;
    else if (!want && el.volume === 0) el.volume = 1;
  };
  try {
    el.addEventListener("volumechange", enforce);   // cualquier des-mute externo (vendor/startAudio) se revierte al instante
    el.addEventListener("playing", enforce);
    enforce();                                      // hidratación: el estado persistido se aplica YA, antes de sesión alguna
  } catch (_) {}
}
// La voz arranca ACTIVA por defecto (icono activo, sonando). Tras un reset del agente se vuelve a este estado.
export function unmuteVoice() {
  store.setBotMuted(false);
  try { localStorage.setItem("hb_bot_muted", "0"); } catch (_) {}
  applyBotMute();
}
export function getStream() { return stream; }
export function getDc() { return null; }         // no raw data channel; kept for interface compat
export function getGate() { return null; }       // speaker-gate is server-side now
export function getAudit() { return audit; }
export function isActive() { return started; }

// ---- mic / camera toggles ----
export function applyMic() {
  if (room && room.localParticipant) { try { room.localParticipant.setMicrophoneEnabled(!store.micMuted()); } catch (_) {} }
  if (stream) stream.getAudioTracks().forEach(t => t.enabled = !store.micMuted());
}
export function applyCam() { if (stream) stream.getVideoTracks().forEach(t => t.enabled = !store.camOff()); }
export function toggleMic() {
  const next = !store.micMuted(); store.setMicMuted(next); localStorage.setItem("hb_mic_muted", next ? "1" : "0"); applyMic();
}
export function applyBotMute() {
  if (!botAudioEl) return;
  botAudioEl.muted = store.botMuted();
  botAudioEl.volume = store.botMuted() ? 0 : 1;   // cinturón: volumen 0 silencia aunque el vendor des-mutee el elemento
}
export function toggleBotMute() {
  const next = !store.botMuted(); store.setBotMuted(next); localStorage.setItem("hb_bot_muted", next ? "1" : "0");
  applyBotMute();
  // EL ICONO MANDA (V2-087). Antes había DOS interruptores para una sola cosa: este (mute del <audio> local) y la
  // síntesis del server, que gobernaba SOLO `chatOpen`. Con el chat abierto podías pulsar 🔊, el icono se ponía
  // en ON, salía el aviso «con voz»… y no sonaba nada, porque el server seguía sin sintetizar. El icono MENTÍA y
  // parecía bloqueado. Ahora el server sigue al icono: el chat abierto sigue silenciando por defecto (ahorra
  // latencia y coste de TTS), pero el operador puede recuperar la voz con un clic sin cerrar el chat.
  setVoiceOutput(!next);
  store.setVoiceFlash({ text: next ? t("voice.flash_muted") : t("voice.flash_voice_on"), show: true });
  clearTimeout(toggleBotMute._t); toggleBotMute._t = setTimeout(() => store.setVoiceFlash(f => ({ ...f, show: false })), 1600);
}
export async function toggleCam() {
  const next = !store.camOff(); store.setCamOff(next); localStorage.setItem("hb_cam_off", next ? "1" : "0");
  if (!next && stream && stream.getVideoTracks().length === 0) {
    try {
      const vs = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: "user" } });
      vs.getVideoTracks().forEach(t => stream.addTrack(t)); if (videoEl) videoEl.srcObject = stream;
    } catch (e) { console.warn("camera unavailable:", e); }
  }
  applyCam();
}

async function populateMicPicker() {
  try {
    const devs = await navigator.mediaDevices.enumerateDevices();
    const ins = devs.filter(d => d.kind === "audioinput");
    const sel = document.getElementById("micsel"); if (!sel) return; sel.innerHTML = "";
    const cur = stream && stream.getAudioTracks()[0] && stream.getAudioTracks()[0].getSettings().deviceId;
    ins.forEach(d => { const o = document.createElement("option"); o.value = d.deviceId; o.textContent = d.label || t("voice.mic_fallback", { id: d.deviceId.slice(0, 6) }); if (d.deviceId === (micDeviceId || cur)) o.selected = true; sel.appendChild(o); });
    sel.style.display = "inline-block";
    sel.onchange = () => { micDeviceId = sel.value || null; localStorage.setItem("zaelar_mic", micDeviceId || ""); store.setConnState(t("voice.conn_switching_mic")); stop(); setTimeout(start, 350); };
  } catch (e) { console.warn("enumerateDevices failed:", e); }
}

// Selector de modo de captura (junto al de micro). Cambiar reconecta (aplica al abrir getUserMedia).
function populateMicModePicker() {
  const sel = document.getElementById("micmode"); if (!sel) return;
  const cur = micMode();
  const opts = [
    ["isolate", t("voice.micmode_isolate")],
    ["full", t("voice.micmode_full")],
    ["raw", t("voice.micmode_raw")],
  ];
  sel.innerHTML = "";
  opts.forEach(([v, label]) => { const o = document.createElement("option"); o.value = v; o.textContent = label; if (v === cur) o.selected = true; sel.appendChild(o); });
  sel.style.display = "inline-block";
  sel.onchange = () => {
    localStorage.setItem("zaelar_micmode", sel.value);
    store.setConnState(t("voice.conn_switching_capture")); stop(); setTimeout(start, 350);
  };
}

// Clean exit from a `start()` that has already been invalidated. Releases whatever this startup opened, and leaves.
//
// WHAT IT DELIBERATELY DOES **NOT** DO: touch `started`/`starting`. The one who invalidated us was `stop()`, which
// already left them as it should; and by the time we get here there may be ANOTHER `start()` under way — the
// `stop(); setTimeout(start, 350)` pattern of a mic swap or a reconnect — whose flags we would trample. Fixing one
// race cannot consist of opening the next.
function _abortedStartup(gen, captured) {
  try { if (captured) captured.getTracks().forEach(tr => tr.stop()); } catch (_) {}
  // Visible, not silent: if this shows up often, something is stopping the session behind the operator's back.
  console.warn(`session.start: aborted mid-startup — the session was stopped while coming up (gen ${gen} ≠ ${_gen})`);
  try { api.clientLog("⏹️ startup aborted", { text: `the session was stopped while coming up (gen ${gen}≠${_gen})`, state: "aborted" }); } catch (_) {}
}

export async function start() {
  if (started || starting) return;
  const gen = _gen;   // see the SESSION GENERATION note above: if it bumps, this startup is no longer the current one
  starting = true; store.setStarting(true); store.setConnState(t("voice.conn_requesting"));
  audit.silent = false; store.setMicBlocked({ show: false, msg: "" });

  // ⏻ GATE against the SERVER'S TRUTH (V2-092 gap, 2026-08-15). `store.powerOff()` is a LOCAL mirror
  // (localStorage) that starts at `false` on any tab/profile that never clicked ⏻ ITSELF — a fresh window
  // reaches here just the same while the engine is stopped elsewhere. Without this gate, the mic is already
  // requested and `api.obsSessionStart()` (below) already opens a real observability session BEFORE main.js's
  // async reconciliation (which runs in parallel, not before) finds out the server is stopped and tears it
  // down — that's the ghost session the master used to show. Asking the server's truth HERE, before touching
  // anything, makes "stopped" mean nothing happens, not "something happens and gets undone afterwards".
  try {
    const rs = await api.runState();
    if (rs && rs.running === false) {
      store.setPowerOff(true); store.setMicMuted(true); store.setBotMuted(true);
      starting = false; store.setStarting(false); store.setConnState("—");
      if (!_everBooted) _unblockBoot();   // don't leave the UI stuck on the splash: there's nothing to wait for
      return;
    }
  } catch (_) { /* verdad del servidor desconocida (aún no responde) — seguir con el estado local, como siempre */ }

  // GATE de SESIÓN ÚNICA: antes de tocar el micro, pide ser la única sesión viva. Si otra pestaña/navegador la
  // tiene, NO abrimos el micro (evita dos micros); avisamos y reintentamos solos hasta que la otra se cierre.
  const acq = await api.sessionAcquire(SID);
  if (acq && acq.ok === false) {
    starting = false; store.setStarting(false); started = false; store.setStarted(false); store.setConnState("—");
    store.setMicBlocked({ show: true, msg: t("voice.session_open_other_tab") });
    if (_blockedRetry) clearTimeout(_blockedRetry);
    _blockedRetry = setTimeout(() => { _blockedRetry = null; start(); }, 3000);
    if (!_everBooted) _unblockBoot();   // no dejes la UI atrapada en el splash mientras está bloqueada
    return;
  }
  if (_blockedRetry) { clearTimeout(_blockedRetry); _blockedRetry = null; }
  if (!_everBooted) {
    clearTimeout(_bootTimer);
    // 60s: generous on purpose. A cold boot pays Hermes's briefing fetch (≤15s) PLUS the fast layer's own
    // first-turn latency on a LOCAL Ollama model (measured 4-36s depending on how warm it is) — bailing early
    // would unblock the UI before zaelar actually greets you, which reads as more broken, not less.
    _bootTimer = setTimeout(() => { console.warn("boot overlay: safety timeout, unblocking anyway"); _unblockBoot(); }, 60000);
  }
  try {
    await api.setVoiceConfig(store.voiceIdx());
    // Local mic capture (for the analyser + to publish). El modo decide el acondicionamiento de la señal (ver arriba).
    const mode = micMode();
    const ad = { ..._MIC_MODES[mode], channelCount: 1 };
    if (micDeviceId) ad.deviceId = { ideal: micDeviceId };
    const captured = await navigator.mediaDevices.getUserMedia({ audio: ad });
    // An open mic is a RESOURCE, not a value: if the session was stopped while the browser asked for permission,
    // it has to be closed here and now. `stop()` already went by — when it ran, `stream` was still null — and
    // nobody else will do it: the operator would be left with the browser's red dot lit over a stopped agent.
    if (gen !== _gen) return _abortedStartup(gen, captured);
    stream = captured;
    _bootPhase("voz");   // mic granted — the voice link is coming up (frontend-known milestone)
    await populateMicPicker();
    populateMicModePicker();
    if (!store.camOff()) {
      try { const vs = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: "user" } }); vs.getVideoTracks().forEach(t => stream.addTrack(t)); }
      catch (e) { console.warn("camera unavailable (audio continues):", e); }
    }
    // After enumerating devices and (maybe) asking for the camera, two more `await`s have gone by. Here `stop()`
    // would have closed the mic and set `stream = null`, so carrying on means `initMic(null)` — the original error.
    if (gen !== _gen) return _abortedStartup(gen, null);
    if (videoEl) videoEl.srcObject = stream;
    started = true; store.setStarted(true);
    api.obsSessionStart("voice");   // abre (o reengancha) la sesión de trabajo que agrupa los eventos — ver api.js
    audio.initMic(stream);   // AudioContext + mic analyser → orb visualiser + mic-level meter keep working

    // --- LiveKit room ---
    const { token, url, ok } = await api.lkToken();
    // Backstop for the gate above: if the server stopped right in this gap (between the initial check and
    // here), `/api/token` says so with a 409 instead of a JWT. Undo what's ALREADY open (mic + observability
    // session) instead of carrying `token: undefined` forward into a LiveKit room that will never connect.
    if (!ok) {
      started = false; store.setStarted(false);
      store.setPowerOff(true); store.setMicMuted(true); store.setBotMuted(true);
      api.obsSessionEnd("engine_stopped");
      try { stream.getTracks().forEach((tr) => tr.stop()); } catch (_) {}
      starting = false; store.setStarting(false); store.setConnState("—");
      if (!_everBooted) _unblockBoot();
      return;
    }
    if (gen !== _gen) return _abortedStartup(gen, null);   // do not build a room for a session that no longer exists
    room = new Room({ adaptiveStream: false, dynacast: false });
    room.on(RoomEvent.TrackSubscribed, (track) => {
      // INSTRUMENTACIÓN (2026-07-23, "no suena nada" sin causa server-side aparente): el server confirma TTS
      // real (TTSMetrics con audio>0) pero el operador no oye nada — hay que ver EXACTAMENTE dónde se rompe en el
      // navegador, en el mismo stream de observabilidad (kind="client", /debug + timeline). No condiciona nada,
      // solo reporta — best-effort, nunca puede romper la reproducción real.
      try {
        api.clientLog("🔈 TrackSubscribed", {
          text: `kind=${track.kind} hasEl=${!!botAudioEl}`,
          state: track.kind,
        });
      } catch (_) {}
      if (track.kind !== "audio" || !botAudioEl) return;
      try { track.attach(botAudioEl); } catch (e) {
        try { api.clientLog("⚠️ track.attach() threw", { text: String((e && e.message) || e) }); } catch (_) {}
      }
      applyBotMute();   // el attach del vendor SIEMPRE des-mutea (attachToElement) → re-asertar muted+volume
      try {
        api.clientLog("🔈 bot audio: estado tras attach", {
          text: `muted=${botAudioEl.muted} volume=${botAudioEl.volume} paused=${botAudioEl.paused} `
              + `readyState=${botAudioEl.readyState} hasSrcObject=${!!botAudioEl.srcObject}`,
          muted: botAudioEl.muted, state: localStorage.getItem("hb_bot_muted"),
        });
      } catch (_) {}
      if (botAudioEl.play) botAudioEl.play().then(() => {
        store.hideAlert();
        try {
          api.clientLog("🔈 play() OK", {
            text: `muted=${botAudioEl.muted} volume=${botAudioEl.volume} paused=${botAudioEl.paused}`,
          });
        } catch (_) {}
      }).catch((e) => {
        // AQUÍ es donde una política de autoplay del navegador (Chrome exige gesto del usuario) bloquea el sonido
        // en silencio para el operador — SIN esto no había forma de verlo desde el server.
        try { api.clientLog("⚠️ play() RECHAZADO (posible bloqueo de autoplay)", { text: String((e && e.name) || e) + ": " + String((e && e.message) || "") }); } catch (_) {}
        store.showAlert(t("voice.alert_tap_audio"), () => botAudioEl.play().catch(() => {}));
      });
      try { audio.attachBot(new MediaStream([track.mediaStreamTrack])); } catch (_) {}
    });
    room.on(RoomEvent.ConnectionStateChanged, (st) => {
      if (st === ConnectionState.Connected) {
        store.setConnState(t("voice.conn_connected"), true); store.hideAlert();
        _recTries = 0;                                   // link is back → refresca el presupuesto de reintentos
        if (_recTimer) { clearTimeout(_recTimer); _recTimer = null; }   // cancela cualquier reintento en cola
        // RECONCILIA el canvas: el servidor puede haberse reiniciado con la página abierta → su `open_widgets`
        // quedó vacío/obsoleto mientras la pantalla seguía mostrando widgets, y NADIE lo re-empujaba hasta el
        // siguiente cambio de canvas → el cerebro "no sabía" lo que el operador tenía delante (o creía haber
        // abierto algo que no). El frontend es AUTORITATIVO: al (re)conectar re-reporta su set REAL de abiertos.
        try { window.__zaelarDesktop && window.__zaelarDesktop._reportOpen(); } catch (_) {}
        // RECONCILIA la síntesis de voz (bug 2026-07-23): setVoiceOutput() viaja por un dato "fire-and-forget"
        // SIN ack — si el mensaje se perdió en una reconexión a medias, el server podía quedar con audio_enabled
        // en False (modo chat) PARA SIEMPRE aunque el chat ya estuviera cerrado en el cliente ("no suena ni
        // subtitula" con el chat cerrado). Al (re)conectar, el cliente es AUTORITATIVO: re-afirma el estado REAL
        // deseado — mismo patrón que la reconciliación del canvas de arriba.
        // V2-087: la verdad es el ICONO (`botMuted`), no `chatOpen`. Antes esto reconciliaba contra el chat, así
        // que una reconexión DESHACÍA el «quiero oírte con el chat abierto» que el operador acabara de pedir.
        setVoiceOutput(!store.botMuted());
        _flushPendingText();
      }
      else if (st === ConnectionState.Reconnecting) store.setConnState(t("voice.conn_reconnecting"));
      else if (st === ConnectionState.Disconnected) { store.setConnState("—"); if (started) store.setBotSpeaking(false); }
      else store.setConnState(String(st));
    });
    room.on(RoomEvent.Disconnected, () => { if (started) autoReconnect(); });
    // Debug-bus contract messages (topic "vl2", voice/engine/pipeline/instrument.py). During the FIRST boot the
    // agent reports ordered milestones — {type:"boot", phase:"memoria"|"reflejo"} as each subsystem comes online —
    // and finally {type:"ready"} = init done (voice live + memory composed + warm), emitted BEFORE zaelar greets.
    room.on(RoomEvent.DataReceived, (payload, _participant, _kind, topic) => {
      if (topic !== "vl2" || _everBooted) return;
      try {
        const m = JSON.parse(new TextDecoder().decode(payload));
        if (m.type === "ready") _unblockBoot();
        else if (m.type === "boot" && m.phase) _bootPhase(m.phase);
      } catch (_) {}
    });
    // AUDIO-SYNCED CAPTIONS: LiveKit forwards the agent's transcription incrementally, paced to its audio playout
    // (TextSynchronizer). Each segment carries a cumulative `text` + `final`. We feed the AGENT's (remote) segments
    // to the live caption overlay — the operator's own STT (local participant) is handled via SSE, not here.
    room.on(RoomEvent.TranscriptionReceived, (segments, participant) => {
      if (participant && participant.isLocal) return;
      for (const s of (segments || [])) store.pushCaptionSeg(s.id, s.text, s.final);
    });

    store.setConnState(t("voice.conn_connecting"));
    await room.connect(url, token);
    // Connecting to the room is the longest `await` of all. If we were invalidated during it, `stream` is null and
    // this very line would blow up just like the `initMic` one — and we would leave a connected room behind as well.
    if (gen !== _gen) { try { await room.disconnect(); } catch (_) {} return _abortedStartup(gen, null); }
    // Publish the mic track we already captured (so the analyser and the published audio are the SAME track).
    const micTrack = stream.getAudioTracks()[0];
    if (micTrack) await room.localParticipant.publishTrack(new LocalAudioTrack(micTrack));
    applyMic(); applyCam();
    openSSE(window.__zaelarDesktop);   // backend→UI events (widgets, bot_speech, transcript, alerts) — same as before
    _startHeartbeat();                 // mantener el lock de sesión única mientras estamos vivos
    starting = false; store.setStarting(false);
  } catch (err) {
    starting = false; store.setStarting(false); started = false; store.setStarted(false); store.setConnState("error"); console.error(err);
    const n = err && err.name;
    if (n === "NotReadableError" || n === "NotAllowedError" || n === "OverconstrainedError") {
      store.setMicBlocked({ show: true, msg: n === "NotAllowedError" ? t("voice.mic_denied") : t("voice.mic_in_use") });
    }
    if (!_everBooted) _unblockBoot();   // a failed boot must never leave the UI locked — let the user retry
    try { await stop(); } catch (_) {}
  }
}

// Auto-reconexión RESILIENTE a cambios de red (fix 2026-07-29). El detonante típico —moverse de wifi a hotspot o a
// otra casa— puede tardar 5-15s en asentar (DHCP + asociación wifi), así que 2 intentos rápidos (lo de antes) SIEMPRE
// fallaban y caían en "Lost connection". Ahora reintentamos con BACKOFF a lo largo de una ventana amplia (~40s),
// mostrando el estado transitorio "reconectando…" (como Zoom/Meet — nunca "recarga la página"). La señalización va
// por loopback (sobrevive al cambio de IP) y el server ya NO fija node-ip (ofrece la IP actual), así que un intento
// hecho DESPUÉS de que la red asiente reconecta solo. Solo si la ventana entera se agota avisamos en la banda
// superior (con reintento), y AUN así seguimos intentando en segundo plano. + escuchamos el evento `online` del
// navegador para reconectar YA en cuanto vuelve la red, sin esperar al siguiente tick del backoff.
let _recTries = 0, _recTimer = null;
const _REC_BACKOFF = [1000, 2000, 3000, 5000, 8000, 8000, 8000, 8000];   // ~43s de ventana; cubre un cambio de red
function autoReconnect() {
  if (!started || _recTimer) return;                    // ya hay un reintento en cola → no solapar
  const i = Math.min(_recTries, _REC_BACKOFF.length - 1);
  if (_recTries >= _REC_BACKOFF.length) {               // ventana agotada → avisa (banda superior) pero SIGUE sola
    store.showAlert(t("voice.alert_lost_network"),
      () => { _recTries = 0; if (_recTimer) { clearTimeout(_recTimer); _recTimer = null; } stop(); setTimeout(start, 300); });
  }
  _recTries++; store.setConnState(t("voice.conn_reconnecting"));
  stop();
  _recTimer = setTimeout(() => { _recTimer = null; if (started) start(); }, _REC_BACKOFF[i]);
}
// La red volvió (cambio de wifi/hotspot completado) → si tenemos sesión, reconecta YA sin esperar al backoff.
try {
  window.addEventListener("online", () => {
    if (!started) return;
    _recTries = 0; if (_recTimer) { clearTimeout(_recTimer); _recTimer = null; }
    store.setConnState(t("voice.conn_reconnecting")); stop(); setTimeout(start, 500);
  });
} catch (_) {}

export async function stop() {
  _gen++;   // invalidates any `start()` in flight — see the SESSION GENERATION note above
  const a = botAudioEl;
  try { if (a) { a.pause(); a.srcObject = null; a.removeAttribute("src"); a.load(); } } catch (_) {}
  _stopHeartbeat();   // deja de renovar el lock; el TTL del server lo libera solo, o `pagehide` al cerrar la pestaña
  started = false; starting = false; store.setStarted(false); store.setStarting(false);
  try { if (room) await room.disconnect(); } catch (_) {} room = null;
  // OJO: aquí NO se cierra el stream de /events. Desde 2026-08-09 lo abre `main.js` en el arranque y su vida es la
  // de la APLICACIÓN, no la de la sesión de voz: por él llegan los eventos de widget (un worker empujando
  // resultados uno a uno), que tienen que seguir pintándose con la voz parada. Cerrarlo aquí dejaba la pantalla
  // congelada en dos casos reales y silenciosos — el operador que para la voz, y el navegador que DENIEGA el
  // micrófono (start() falla → pasa por aquí → adiós al stream que main.js acababa de abrir).
  if (stream) { try { stream.getTracks().forEach(t => t.stop()); } catch (_) {} stream = null; }
  // SOLTAR EL AUDIO DE VERDAD (2026-08-10): antes solo se dejaba caer el analizador del BOT (`dropBot`) y el del
  // MICRO sobrevivía a `stop()` con su AudioContext abierto — de ahí que el visualizador tuviera que gatearse por
  // `agentLive()` para no seguir publicando nivel de un micro parado. Ahora se cierra el grafo entero, así que
  // «parado» es parado en la realidad y no solo en el icono; y queda la línea en observabilidad que lo demuestra.
  store.setBotSpeaking(false); audio.reset("session_stop");
  store.setConnState("—"); store.setLatency("— ms");
}

export async function reset() { await stop(); try { await api.reset(); } catch (_) {} }

// Bug real 2026-07-23 (reporte del operador con captura): resetHard/resetFull hacían `await stop()` ANTES de pedir
// el reset al server — `stop()` cierra la conexión SSE de sse.js (la que enruta "widget close" → desktop.closeAll()),
// así que cuando el server difundía el cierre YA no había nadie escuchando en ese canal. El panel de observabilidad
// SÍ mostraba "close mensajeria"/"close cluster-registro" porque debugbus.js mantiene su PROPIA conexión SSE
// independiente (para poder depurar incluso sin sesión de voz) — pero esa conexión solo alimenta el log, nunca
// llama a desktop. Resultado: nada se cerraba en pantalla, el localStorage `hb_desktop` (que solo `closeAll()`
// limpia) seguía intacto → un refresh restauraba los mismos widgets. Fix: limpiar escritorio + log EN EL CLIENTE,
// de forma optimista y determinista, en vez de depender de un viaje de ida y vuelta por un canal que vamos a matar.
function _clearCanvasAndLog() {
  try { window.__zaelarDesktop && window.__zaelarDesktop.closeAll(); } catch (_) {}
  try { clearDebugBuffer(); } catch (_) {}
}

// Un reset deja el sistema LISTO PARA EMPEZAR — y eso incluye la voz (fix 2026-08-12).
//
// Fallo REAL medido: el operador apretó Reset a las 13:21:46 y la voz no volvió hasta las 13:22:49 — **61 segundos**
// con el ⏻ parpadeando en ámbar. No era un arranque lento: no había ningún arranque. `stop()` tumba la sesión y
// NADIE la levantaba; el único que re-arma es `ensureVoice()` de main.js, que solo corre al cargar la página y en
// cada `pointerdown` — y el clic que dispara el reset llega ANTES del `stop()`, así que ese re-armado se desperdicia.
// La voz se quedaba esperando el SIGUIENTE clic del operador, que tardó un minuto en llegar. El comentario de
// `ensureVoice` presumía de «re-arms after Reset»: no era verdad por este camino.
//
// Se re-arma aquí, que es además donde toca: seguimos dentro del gesto del usuario (acaba de pulsar el botón de
// confirmar), así que el navegador concede micro/audio sin pelear — que es la razón por la que ese re-armado cuelga
// de `pointerdown` y no de un temporizador.
async function _rearmVoiceAfterReset() {
  if (store.powerOff()) return;              // ⏻ apagado A PROPÓSITO: un reset no desobedece al operador
  await new Promise(r => setTimeout(r, 450));  // deja cerrar la Room anterior (mismo settle que reconnect())
  try { await start(); } catch (_) {}
}

// HARD reset (botón Reset, tras confirmación): para la voz, dispara el /reset/hard del server (congela el trabajo
// en curso en la memoria de estado + registra la orden en corto + MATA los procesos de fondo) y limpia los blobs
// de actividad del canvas en el cliente.
export async function resetHard() {
  _clearCanvasAndLog();
  await stop();
  try { await api.resetHard(); } catch (_) {}
  try { store.setTasks([]); } catch (_) {}          // fuera las "nubes" de actividad de fondo del canvas
  unmuteVoice();   // tras un RESET del agente, la voz arranca ACTIVA (icono activo) por defecto
  await _rearmVoiceAfterReset();
}
// Reset CON CHECKBOXES (V2-063, diálogo del botón Reset): opts = {wipeMemory, wipeCredentials}. Si CUALQUIERA es
// true el server SE REINICIA SOLO (SQLite/perfiles en uso) — no hay sesión a la que volver hasta que responda de
// nuevo, así que en vez de re-`start()` (como resetHard) esperamos con un overlay y recargamos la página entera
// cuando vuelva: más simple y robusto que intentar resucitar la Room de LiveKit a medio camino de un reinicio.
export async function resetFull({ wipeMemory = false, wipeCredentials = false } = {}) {
  _clearCanvasAndLog();
  await stop();
  let res = {};
  try { res = await api.resetFull({ wipe_memory: wipeMemory, wipe_credentials: wipeCredentials }); } catch (_) {}
  if (!res || !res.restarting) {
    // El caso NORMAL del botón Reset (sin borrar memoria ni credenciales): el server sigue vivo, así que la voz
    // vuelve YA. Sin esto el reset dejaba el agente en `stalled` — el ámbar parpadeante — hasta el siguiente clic.
    try { store.setTasks([]); } catch (_) {}
    unmuteVoice();
    await _rearmVoiceAfterReset();
    return;
  }
  store.setRestarting(true);
  const deadline = Date.now() + 45000;      // reinicio típico ~8-10s; generoso por si el arranque va lento
  (async function poll() {
    while (Date.now() < deadline) {
      await new Promise(r => setTimeout(r, 1500));
      try {
        const r = await fetch("/api/status", { cache: "no-store" });
        if (r.ok) { location.reload(); return; }
      } catch (_) { /* server todavía caído — sigue esperando */ }
    }
    store.setRestarting(false);   // se acabó la paciencia: deja que el operador recargue a mano
  })();
}
export function toggle() { (started || starting) ? stop() : start(); }
export async function reconnect() {
  if (!started && !starting) return start();
  await stop();
  await new Promise(r => setTimeout(r, 450));
  return start();
}

// ---- text channel: publish a typed/pasted message; the embedded agent injects it as a user turn ----
// NOTE (INI-012 remaining wiring): the agent entrypoint must subscribe to this data topic and call
// session.generate_reply(user_input=text). Until then, chat text is delivered best-effort over the room data.
//
// Bug real 2026-07-24 (reporte del operador, con timeline confirmado): mandar un mensaje justo cuando la sala
// aún no estaba en estado Connected (p.ej. recién reconectada) lo DESCARTABA en silencio — `sendText` devolvía
// `true` igualmente, y `ChatWall.js::submitChat` lo añade al historial SIN comprobar el resultado → el mensaje
// aparecía "enviado" en pantalla pero nunca llegaba al cerebro. Lo que respondía después (el saludo de kickoff)
// no tenía relación alguna con lo que el operador había escrito. Fix: si no está conectado, se ENCOLA (no se
// tira) y se entrega en cuanto la sala llega a Connected (`_flushPendingText`, enganchado en
// RoomEvent.ConnectionStateChanged más arriba) — nunca más un mensaje visible-pero-fantasma.
let _pendingText = [];
function _flushPendingText() {
  if (!_pendingText.length || !room || room.state !== ConnectionState.Connected) return;
  const queued = _pendingText; _pendingText = [];
  for (const t of queued) _publishText(t);
}
function _publishText(t) {
  try {
    const payload = new TextEncoder().encode(JSON.stringify({ t: "zaelar-text", text: t }));
    room.localParticipant.publishData(payload, { reliable: true, topic: "zaelar-text" });
    return true;
  } catch (_) { return false; }
}
export function sendText(text) {
  const t = (text || "").trim(); if (!t) return false;
  if (!room || room.state !== ConnectionState.Connected) {
    _pendingText.push(t);
    if (!started && !starting) start().catch(() => {});
    return true;
  }
  return _publishText(t);
}

// MODO CHAT = VOZ OFF (V2-054 T1.2): activa/desactiva la SÍNTESIS de voz del server (topic zaelar-voice).
// Con audio OFF el pipeline de LiveKit NO invoca el TTS (rama text-only) → sin latencia ni coste de síntesis;
// la respuesta sigue apareciendo en el ChatWall por SSE. Best-effort: si no hay sesión, no-op (al conectar el
// efecto de ChatWall lo re-aplica).
export function setVoiceOutput(enabled) {
  if (!room || room.state !== ConnectionState.Connected) return false;
  try {
    const payload = new TextEncoder().encode(JSON.stringify({ t: "zaelar-voice", audio: enabled !== false }));
    room.localParticipant.publishData(payload, { reliable: true, topic: "zaelar-voice" });
    return true;
  } catch (_) { return false; }
}

// ---- voice picker (tap the orb to cycle interlocutor; applies on reconnect) ----
export async function loadVoices() { const d = await api.voices(); store.setVoices(d.voices || []); store.setVoiceIdx(d.current || 0); }
function flashVoice() {
  const v = store.voices(); if (!v.length) return;
  store.setVoiceFlash({ text: "🗣 " + v[store.voiceIdx()], show: true });
  clearTimeout(flashVoice._t); flashVoice._t = setTimeout(() => store.setVoiceFlash(f => ({ ...f, show: false })), 1800);
}
export async function cycleVoice() {
  if (!store.voices().length) await loadVoices(); if (!store.voices().length) return;
  store.setVoiceIdx((store.voiceIdx() + 1) % store.voices().length); flashVoice();
  await api.setVoiceConfig(store.voiceIdx());
  if (started) { await reset(); start(); }
}

// ---- speaker-gate is server-side now: these are no-ops kept for interface compatibility ----
export function setGate(on) { store.setGateOn(on !== false); return "voice filter is server-side on the LiveKit engine"; }
export function retrain() {}
export function setOrb(s) { const v = s === "friendly" ? "friendly" : "pro"; store.setOrbStyle(v); localStorage.setItem("zaelar_orb", v); return "orb: " + v; }

export function startVisuals({ orbCanvas, vizCanvas }) {
  startVisualizer({ orbCanvas, vizCanvas, getStream, getGate, audit });
}
