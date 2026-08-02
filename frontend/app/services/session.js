// ============================================================================
// session.js — the voice session ENGINE. Owns the imperative runtime (RTCPeer-
// Connection, data channel, mic/camera MediaStream, speaker gate) and the
// start/stop/reset/auto-reconnect lifecycle. Logic ported VERBATIM from the
// original assistant inline script — only the DOM writes were swapped for reactive
// store updates, and the helpers (audio/vad/stt/sse/visualizer/api) were extracted.
//
// This module is the least framework-coupled part of the UI: under Solid it stays
// almost exactly as-is (it already touches no JSX).
// ============================================================================
import * as store from "../core/store.js?v=2";
import * as audio from "./audio.js?v=2";
import * as api from "./api.js?v=2";
import { SpeakerGate } from "../lib/speaker-gate.js?v=2";
import { startMicVAD, stopMicVAD } from "./vad.js?v=2";
import { startBrowserSTT, stopBrowserSTT } from "./stt.js?v=2";
import { openSSE, closeSSE } from "./sse.js?v=4";
import { startVisualizer } from "./visualizer.js?v=2";

// ---- imperative runtime state (mirrors the old module-level globals) ----
let pc = null, dc = null, stream = null, gate = null, videoEl = null, botAudioEl = null;
let started = false, starting = false;            // synchronous guards (store mirrors for the UI)
let _recTries = 0, _wasConnected = false;         // auto-reconnect: only after a link was established then dropped
let micDeviceId = localStorage.getItem("zaelar_mic") || null;
const audit = { silent: false };                  // true if the browser captured silence (mic busy / level 0)
let _txSeq = 0;                                    // monotonic id for typed/pasted text messages
const _pendingText = [];                           // text queued while the data channel isn't open yet

// injected by the components/main on mount
export function attachVideo(el) { videoEl = el; }
export function attachBotAudio(el) {
  botAudioEl = el;
  // PARIDAD icono↔audio — INVARIANTE AUTO-CORRECTIVA (espejo de session-lk.js, bug de hidratación 2026-07-17):
  // cualquier cambio externo de muted/volume dispara 'volumechange' → re-asertamos el estado del signal (guard
  // anti-recursión) + cinturón volume=0 + hidratación inmediata del estado persistido al montar.
  const enforce = () => {
    const want = store.botMuted();
    if (el.muted !== want) el.muted = want;
    if (want && el.volume !== 0) el.volume = 0;
    else if (!want && el.volume === 0) el.volume = 1;
  };
  try {
    el.addEventListener("volumechange", enforce);
    el.addEventListener("playing", enforce);
    enforce();
  } catch (_) {}
}
export function unmuteVoice() {
  store.setBotMuted(false);
  try { localStorage.setItem("hb_bot_muted", "0"); } catch (_) {}
  applyBotMute();
}
export function getStream() { return stream; }
export function getDc() { return dc; }
export function getGate() { return gate; }
export function getAudit() { return audit; }
export function isActive() { return started; }

// ---- owner-voice indicator (speaker gate) → store ----
function spkState(s) {
  if (!store.gateOn()) { store.setSpk({ show: true, other: false, html: "🎙 voice filter: off" }); return; }
  store.setSpk({ show: true, other: false, html: s.enrolled ? "🔊 recognizing your voice" : `🎧 learning your voice… ${s.enrollCount}/${s.need}` });
}
let _spkTimer = null;
function spkOwner(d) {
  if (!store.gateOn()) return;
  if (d.reason === "enroll") store.setSpk({ show: true, other: false, html: `🎧 learning your voice… ${d.count}/5` });
  else if (d.reason === "other") {
    store.setSpk({ show: true, other: true, html: "🚫 <b>another voice</b> (ignored)" });
    clearTimeout(_spkTimer); _spkTimer = setTimeout(() => store.setSpk({ show: true, other: false, html: "🔊 recognizing your voice" }), 1500);
  } else if (d.reason === "owner") store.setSpk({ show: true, other: false, html: "🔊 you" });
}

// ---- mic / camera toggles. State persists across refreshes; here we only apply to the live stream. ----
export function applyMic() {
  if (stream) stream.getAudioTracks().forEach(t => t.enabled = !store.micMuted());   // muted → track sends silence
}
export function applyCam() {
  if (stream) stream.getVideoTracks().forEach(t => t.enabled = !store.camOff());
}
export function toggleMic() {
  const next = !store.micMuted(); store.setMicMuted(next); localStorage.setItem("hb_mic_muted", next ? "1" : "0"); applyMic();
}
// ---- bot audio mute: SILENCE zaelar's voice output without stopping the agent. The WebRTC link, the mic and
// the brain keep running (it still listens, thinks and replies) — we just don't PLAY the incoming audio. State
// persists across refreshes and is honored on (re)connect in pc.ontrack. ----
export function applyBotMute() {
  if (!botAudioEl) return;
  botAudioEl.muted = store.botMuted();
  botAudioEl.volume = store.botMuted() ? 0 : 1;   // cinturón: volumen 0 silencia aunque algo des-mutee el elemento
}
export function toggleBotMute() {
  const next = !store.botMuted(); store.setBotMuted(next); localStorage.setItem("hb_bot_muted", next ? "1" : "0");
  applyBotMute();
  store.setVoiceFlash({ text: next ? "🔇 muted (still running)" : "🔊 voice on", show: true });
  clearTimeout(toggleBotMute._t); toggleBotMute._t = setTimeout(() => store.setVoiceFlash(f => ({ ...f, show: false })), 1600);
}
export async function toggleCam() {
  const next = !store.camOff(); store.setCamOff(next); localStorage.setItem("hb_cam_off", next ? "1" : "0");
  if (!next && stream && stream.getVideoTracks().length === 0) {   // turning ON but no camera track yet → acquire it
    try {
      const vs = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: "user" } });
      vs.getVideoTracks().forEach(t => stream.addTrack(t)); if (videoEl) videoEl.srcObject = stream;
    } catch (e) { console.warn("camera unavailable:", e); }
  }
  applyCam();
}

// ---- diagnostics (kept using getElementById: pure debug surface in the .conn line) ----
function diagMic(tag) {
  try {
    const tr = stream && stream.getAudioTracks()[0];
    if (!tr) { console.warn("diagMic: no audio track (" + tag + ")"); const mv = document.getElementById("micv"); if (mv) mv.textContent = "sin track"; api.clientLog("🎙️ " + tag, { text: "NO audio track" }); return; }
    const st = tr.getSettings();
    console.info("🎙️ [" + tag + "]", tr.label || "(sin nombre)", "· muted:", tr.muted, "· enabled:", tr.enabled, "· state:", tr.readyState, "· settings:", st);
    const mv = document.getElementById("micv"); if (mv) mv.textContent = (tr.label || "micro").slice(0, 22) + (tr.muted ? " ⚠️muted" : "");
    const mbw = document.getElementById("micbarwrap"); if (mbw) mbw.style.display = "inline-block";
    api.clientLog("🎙️ mic " + tag, { device: (tr.label || "(sin nombre)"), muted: tr.muted, enabled: tr.enabled, state: tr.readyState, text: "sr=" + st.sampleRate + " ch=" + st.channelCount + " aec=" + st.echoCancellation });
  } catch (e) { console.warn("diagMic err", e); }
}
// Decisive test: is the BROWSER itself capturing sound? Sample peak RMS for ~2.5s, report it, and if it stays
// flat, surface it on the orb (🚫) — it's an OS-permission / device / exclusive-hold problem, not STT.
function auditMicCapture() {
  let peak = 0; const iv = setInterval(() => { const r = audio.micRMS(); if (r > peak) peak = r; }, 100);
  setTimeout(() => {
    clearInterval(iv);
    const tr = stream && stream.getAudioTracks()[0], dev = tr ? (tr.label || "(sin nombre)") : "(no track)";
    const sp2 = new URLSearchParams(location.search);
    const mode = sp2.get("raw") === "1" ? "raw" : sp2.get("aec") === "1" ? "aec(echoCancel only)" : "full(interviewer: aec+ns+agc+voiceIso)";
    api.clientLog("🔎 mic capture audit", { rms: Math.round(peak * 1000) / 1000, raw: sp2.get("raw") === "1", device: dev, text: (peak > 0.02 ? "OK: browser capturing sound" : "SILENT: browser captures ~0 over 2.5s") + " · dev=" + dev + " · " + mode });
    audit.silent = !store.micMuted() && peak < 0.02;   // si estoy muteado a propósito, el silencio es esperado
    if (audit.silent && micDeviceId) { micDeviceId = null; localStorage.removeItem("zaelar_mic"); }   // drop a silent pinned mic
  }, 2500);
}

async function populateMicPicker() {
  try {
    const devs = await navigator.mediaDevices.enumerateDevices();
    const ins = devs.filter(d => d.kind === "audioinput");
    console.info("🎚️ audioinput devices:", ins.map(d => ({ id: d.deviceId.slice(0, 8), label: d.label })));
    const sel = document.getElementById("micsel"); if (!sel) return; sel.innerHTML = "";
    const cur = stream && stream.getAudioTracks()[0] && stream.getAudioTracks()[0].getSettings().deviceId;
    ins.forEach(d => { const o = document.createElement("option"); o.value = d.deviceId; o.textContent = d.label || ("mic " + d.deviceId.slice(0, 6)); if (d.deviceId === (micDeviceId || cur)) o.selected = true; sel.appendChild(o); });
    sel.style.display = "inline-block";
    sel.onchange = () => { micDeviceId = sel.value || null; localStorage.setItem("zaelar_mic", micDeviceId || ""); store.setConnState("switching mic…"); stop(); setTimeout(start, 350); };
  } catch (e) { console.warn("enumerateDevices failed:", e); }
}

function iceDone(pc) {
  return new Promise(res => {
    if (pc.iceGatheringState === "complete") return res();
    const chk = () => { if (pc.iceGatheringState === "complete") { pc.removeEventListener("icegatheringstatechange", chk); res(); } };
    pc.addEventListener("icegatheringstatechange", chk); setTimeout(res, 2500);
  });
}

export async function start() {
  if (started || starting) return; starting = true; store.setStarting(true); store.setConnState("requesting…");
  audit.silent = false; store.setMicBlocked({ show: false, msg: "" });   // clear any prior mic-blocked state
  try {
    await api.setVoiceConfig(store.voiceIdx());
    // CAPTURE AUDIO ALONE FIRST (decoupled from video): requesting audio+video together can bind the mic to the
    // CAMERA's input. Separate calls → audio uses the chosen (or default) input.
    //   ?aec=1 → echoCancellation only   ·   ?raw=1 → fully raw (headphones only)   ·   default = full interviewer config
    const sp = new URLSearchParams(location.search);
    const micMode = sp.get("raw") === "1" ? "raw" : sp.get("aec") === "1" ? "aec" : "full";
    const ap = micMode === "raw" ? { echoCancellation: false, noiseSuppression: false, autoGainControl: false }
             : micMode === "aec" ? { echoCancellation: true, noiseSuppression: false, autoGainControl: false }
             :                     { echoCancellation: true, noiseSuppression: true, autoGainControl: true, advanced: [{ voiceIsolation: true }] };
    const ad = { ...ap, channelCount: 1 };
    if (micDeviceId) ad.deviceId = { ideal: micDeviceId };   // ideal, NOT exact → a silent/missing pinned device falls back
    stream = await navigator.mediaDevices.getUserMedia({ audio: ad });   // audio-only → system-default mic
    diagMic("after getUserMedia(audio)");
    await populateMicPicker();
    // video is best-effort and MUST NOT block/break audio. Skip it if the camera is toggled OFF.
    if (!store.camOff()) {
      try { const vs = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: "user" } }); vs.getVideoTracks().forEach(t => stream.addTrack(t)); }
      catch (e) { console.warn("camera unavailable (audio continues):", e); }
    }
    if (videoEl) videoEl.srcObject = stream; started = true; store.setStarted(true);
    applyMic(); applyCam();   // honor persisted mic-muted / camera-off on the live stream
    let iceServers = await api.iceServers();
    pc = new RTCPeerConnection({ iceServers });
    dc = pc.createDataChannel("vala-turn");
    dc.onopen = flushPendingText;   // drain any chat/paste text queued before the channel was ready
    // A dead data channel = no turn signals (zaelar seems deaf) while audio still flows. Leave evidence.
    dc.onclose = () => { if (started) api.clientLog("⚠️ data channel CLOSED mid-session", { text: "vala-turn dc closed — turn signals lost" }); };
    dc.onerror = e => api.clientLog("⚠️ data channel ERROR", { text: String((e && e.error) || e) });
    pc.ontrack = e => {
      const a = botAudioEl; if (!a) return; a.srcObject = e.streams[0]; a.muted = store.botMuted();   // honor persisted bot-mute
      if (a.play) a.play().then(store.hideAlert).catch(() => store.showAlert("Tap to enable zaelar's audio.", () => a.play().catch(() => {})));
      audio.attachBot(e.streams[0]);
    };
    pc.onconnectionstatechange = () => {
      if (!pc) return; const c = pc.connectionState; store.setConnState(c, c === "connected");
      if (c === "connected") { _wasConnected = true; _recTries = 0; store.hideAlert(); return; }
      if (!started || starting) return;
      // Only recover a link that WAS established and THEN failed — never thrash during initial setup.
      if (c === "failed" && _wasConnected) autoReconnect();
    };
    stream.getAudioTracks().forEach(t => pc.addTrack(t, stream));
    audio.initMic(stream);   // AudioContext + mic analyser (fftSize 2048 for pitch)
    // Speaker-gate is OFF by default: only create it when opted-in via window.zaelar.gate(true) then reconnect.
    if (store.gateOn()) { gate = new SpeakerGate(audio.micAnalyser(), audio.context().sampleRate, { enabled: true, onState: spkState }); gate.reset(); spkState({ enrolled: false, enrollCount: 0, need: 5 }); }
    else { gate = null; store.setSpk({ show: false, other: false, html: "" }); }
    startMicVAD({ getStream, getDc, getGate, onOwner: spkOwner }); openSSE(window.__zaelarDesktop); auditMicCapture();
    // free browser STT if the server is configured for it (STT_PROVIDER=browser)
    api.sttMode().then(m => { if (m && m.mode === "browser") startBrowserSTT(m.lang, { getDc, isActive }); }).catch(() => {});
    const offer = await pc.createOffer({ offerToReceiveAudio: true }); await pc.setLocalDescription(offer);
    await iceDone(pc); store.setConnState("connecting…");
    const r = await api.sendOffer(pc.localDescription);
    if (!r.ok) { store.setConnState("error " + r.status); starting = false; store.setStarting(false); stop(); return; }
    await pc.setRemoteDescription(await r.json());
    starting = false; store.setStarting(false);
  } catch (err) {
    starting = false; store.setStarting(false); started = false; store.setStarted(false); store.setConnState("error"); console.error(err);
    // Mic taken by another app (NotReadableError) or denied → show the 🚫 ring on the orb, NOT a top error banner.
    const n = err && err.name;
    if (n === "NotReadableError" || n === "NotAllowedError" || n === "OverconstrainedError") {
      store.setMicBlocked({ show: true, msg: n === "NotAllowedError" ? "🔇 Microphone permission denied" : "🔇 Microphone in use by another app (SuperWhisper?)" });
    } else { store.setConnState("error"); }
  }
}

// Auto-reconnect on a dropped WebRTC link. Silent for the first tries; only bother the user if it can't come back.
function autoReconnect() {
  if (!started) return;
  if (_recTries >= 2) { store.showAlert("Lost the audio connection with zaelar.", () => { _recTries = 0; stop(); setTimeout(start, 300); }); return; }
  _recTries++; _wasConnected = false;   // require a fresh successful connect before another retry → no storms
  store.setConnState("reconnecting…"); console.warn("WebRTC lost → auto-reconnect #" + _recTries);
  stop(); setTimeout(start, 800);
}

export function stop() {
  // KILL the bot's audio FIRST and hard (the Stop button must silence it instantly).
  const a = botAudioEl;
  try { if (a && a.srcObject) { a.srcObject.getTracks().forEach(t => { try { t.stop(); } catch (_) {} }); } if (a) { a.pause(); a.srcObject = null; a.removeAttribute("src"); a.load(); } } catch (_) {}
  api.hangup();   // tell the SERVER to force-stop the agent NOW (keepalive)
  started = false; starting = false; store.setStarted(false); store.setStarting(false);
  try { stopBrowserSTT(); } catch (_) {}
  try { stopMicVAD(); } catch (_) {}
  try { if (pc) pc.close(); } catch (_) {} pc = null; dc = null; closeSSE();
  if (stream) { try { stream.getTracks().forEach(t => t.stop()); } catch (_) {} stream = null; }
  store.setBotSpeaking(false); audio.dropBot();
  gate = null; store.setSpk({ show: false, other: false, html: "" });
  store.setConnState("—"); store.setLatency("— ms");
}

export async function reset() { stop(); await api.reset(); }
// HARD reset (botón Reset, tras confirmación): para la voz + dispara /reset/hard (congela el trabajo en curso en
// la memoria de estado, lo registra en corto y MATA los procesos de fondo) + limpia los blobs de actividad.
export async function resetHard() {
  stop();
  try { await api.resetHard(); } catch (_) {}
  try { store.setTasks([]); } catch (_) {}
  unmuteVoice();   // tras un RESET del agente, la voz arranca ACTIVA (icono activo) por defecto
}
export function toggle() { (started || starting) ? stop() : start(); }

// Clean RE-CONNECT to apply a config change (voice/STT/TTS/language) to the LIVE pipeline. The TTS service is
// built when the pipeline is constructed, so a change can't be hot-swapped mid-stream — we tear the session down
// and bring it straight back up. Callers (settings save, orb voice cycle) MUST have synced store.voiceIdx to the
// server's chosen voice FIRST, so start() re-applies the RIGHT voice (not the stale one).
export async function reconnect() {
  if (!started && !starting) return start();
  stop();
  await new Promise(r => setTimeout(r, 450));   // let the server tear the old worker down before the new offer
  return start();
}

// ---- text channel: send a typed/pasted message to the agent (server's ClientTextInjector turns it into a turn) ----
function _txSend(text) {
  if (!dc || dc.readyState !== "open") return false;
  try { dc.send(JSON.stringify({ label: "rtvi-ai", type: "client-message", id: "tx" + (++_txSeq), data: { t: "vala-text", d: { text } } })); return true; }
  catch (_) { return false; }
}
function flushPendingText() { while (_pendingText.length && _txSend(_pendingText[0])) _pendingText.shift(); }
// Send NOW if connected; otherwise queue it and bring the session up so the agent can consume it on connect.
export function sendText(text) {
  const t = (text || "").trim(); if (!t) return false;
  if (_txSend(t)) return true;
  _pendingText.push(t);
  if (!started && !starting) start();
  return true;
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

// ---- speaker-gate controls (exposed on window.zaelar) ----
export function setGate(on) {
  store.setGateOn(on !== false); localStorage.setItem("zaelar_gate", store.gateOn() ? "1" : "0");
  if (gate) gate.enabled = store.gateOn();
  spkState({ enrolled: gate && gate.enrolled(), enrollCount: 0, need: 5 });
  return "voice filter " + (store.gateOn() ? "ON" : "OFF");
}
export function retrain() { if (gate) { gate.retrain(); spkState({ enrolled: false, enrollCount: 0, need: 5 }); } }
export function setOrb(s) { const v = s === "friendly" ? "friendly" : "pro"; store.setOrbStyle(v); localStorage.setItem("zaelar_orb", v); return "orb: " + v; }

// start the always-on render loop (orb + spectrum). Canvases come from the mounted components.
export function startVisuals({ orbCanvas, vizCanvas }) {
  startVisualizer({ orbCanvas, vizCanvas, getStream, getGate, audit });
}
