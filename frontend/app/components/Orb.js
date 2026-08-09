// Orb — bottom-centre voice orb (zaelar's voice spectrum) = zaelar PERSONIFIED, the LIVE CAPTIONS that crawl up
// from it (Star-Wars style), the activity rail, the transient flash label, the 🚫 mic-blocked ring/caption, and
// — V2-039 «EL OJO» (operator 2026-07-17) — the whole cluster reads as an EYE: the icon arc above is the UPPER
// LID, the ECG arc below (lib/ecg.js) is the LOWER LID, the orb is the IRIS. Both arcs stretch so their tips
// nearly meet at the corners (canthi). SEVEN controls on the upper lid (L→R):
//   🎤 mic      → mute/unmute the OPERATOR'S OWN microphone input. MOVED here 2026-08-09 when the CameraUnit
//                 widget (its former home) was hidden/archived — same session.toggleMic()/store.micMuted() seam.
//   🧠 memory   → open the MEMORY MAP visualizer (state + short/long-term + concept graph, V2-014). BLUE while open.
//   🔊 speaker  → mute/unmute zaelar's voice OUTPUT (the agent keeps running: mic, brain and crons stay live).
//   ⏻ power    → CENTRE (apex). Explicit ON/OFF of the voice session — the ONE exception to always-on: while
//                 off (persisted hb_power_off) main.js does NOT auto-(re)connect; click again to come back.
//   📝 captions → show/hide the live transcript crawling above the orb (history always stays in the chat wall).
//   💬 chat     → open the chat panel (Chat/Processes/Crons/Clusters tabs — crons live INSIDE it, no separate
//                 cron icon any more). MOVED here 2026-08-09, same slot the ⏰ cron shortcut used to occupy;
//                 replaces both that shortcut AND CameraUnit's own chat button (archived along with it).
//   🤖 robot    → attention gate (V2-016). OFF (grey) = `always`; ON (blue) = `wakeword` ("zaelar"/"harvis").
//                 Toggles attention_mode LIVE via the SAME settings seam the ⚙ uses (POST /api/settings).
// All controls are frameless icons: BLUE when ON/open, pale GREY when OFF/closed. The lid arc is drawn by CSS
// (translateY per nth-child: centre highest, outer icons dive to the corners) — UNCHANGED by the 2026-08-09 swap,
// since it's keyed by SLOT INDEX, not which icon sits there. The PROJECT icons (◉ status, ⌗ docs, ◷ debug, ⚙,
// ☾ theme, 🧭, Reset) stay UP in the TopBar — ☾ theme moved there FROM here the same day, next to ⚙. Drag the orb
// to move it (position persisted). The orb canvas is driven by the visualizer; the ECG canvas by lib/ecg.js; the
// activity rail (#activity) is owned by the desktop. Captions are LIVE only (last 3 lines) — the chat wall keeps
// the history.
import { h, raw } from "../core/dom.js?v=2";
import { createEffect, createSignal } from "../core/reactive.js?v=2";
import * as store from "../core/store.js?v=2";
import * as session from "../services/session.js?v=3";
import * as api from "../services/api.js?v=2";
import { makeDraggable } from "../lib/draggable.js?v=2";
import { startEcg } from "../lib/ecg.js?v=2";
import { t } from "../core/i18n.js?v=1";

// Inline SVGs (self-contained, currentColor). Mic + memory + speaker on/off + power + captions + chat + robot.
const MIC_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/></svg>`;
const MEM_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4.5a3 3 0 0 0-3 3 3 3 0 0 0-1.3 5.7A3 3 0 0 0 8 16.5a3 3 0 0 0 4 2.6"/><path d="M12 4.5a3 3 0 0 1 3 3 3 3 0 0 1 1.3 5.7A3 3 0 0 1 16 16.5a3 3 0 0 1-4 2.6"/><path d="M12 4.5v15"/></svg>`;
const SPK_ON  = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M18.5 5.5a9 9 0 0 1 0 13"/></svg>`;
const SPK_OFF = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="m22 9-6 6"/><path d="m16 9 6 6"/></svg>`;
const CAP_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="M7 10h5"/><path d="M7 14h9"/></svg>`;
const CHAT_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.4 9.06 9.06 0 0 1-4-.9L3 21l1.9-4.5a8.38 8.38 0 0 1-.9-4A8.5 8.5 0 0 1 12.5 4 8.38 8.38 0 0 1 21 11.5z"/></svg>`;
const BOT_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect x="4" y="8" width="16" height="12" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M9 13v2"/><path d="M15 13v2"/></svg>`;
const PWR_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.77.04"/></svg>`;

export function Orb() {
  let wrapEl, orbEl, capEl, capInnerEl, ecgEl;

  // ---- attention gate toggle (V2-016). Local signal mirrors config/settings.json's attention_mode: ON = wakeword
  // (only acts on "zaelar"/"harvis"), OFF = always (listens+answers to everything, default). Reflects the REAL
  // current mode on load; toggling writes it LIVE via the same /api/settings seam the ⚙ uses (attention_mode is
  // "live" — voice/attention.py::mode() reads ZAELAR_ATTENTION each turn, no reconnect needed).
  const [wakeOn, setWakeOn] = createSignal(false);
  api.getSettings()
    .then(cfg => {
      const knob = (cfg.knobs || []).find(k => k.key === "attention_mode");
      setWakeOn((knob && knob.value) === "wakeword");
    })
    .catch(() => {});
  const toggleWake = () => {
    const next = !wakeOn();
    setWakeOn(next);                                            // optimistic; reflects immediately
    api.saveSettings({ attention_mode: next ? "wakeword" : "always" })
      .catch(() => setWakeOn(!next));                           // revert on failure
  };

  const wrap = h("div", { id: "orbwrap", class: "orbwrap", ref: el => (wrapEl = el) },
    // OVAL VEIL (operator 2026-07-22, 3rd pass): a big, opaque, blurred backdrop behind the WHOLE eye cluster
    // (icons + orb + ECG), not just the orb canvas — over a busy background (e.g. a video playing in a widget)
    // the frameless icons and the thin ECG line were themselves nearly invisible. z-index:-1 (styles.css) sinks
    // it behind its siblings here WITHOUT leaving .orbwrap's own very-high stacking context, so it still sits
    // above every widget/video on the canvas.
    h("div", { class: "orbveil", "aria-hidden": "true" }),
    h("div", { id: "activity", class: "activity" }),                                   // agent activity (desktop mounts here)
    h("div", { class: () => "vlabel" + (store.voiceFlash().show ? " show" : "") }, () => store.voiceFlash().text),
    h("div", { class: () => "micblockcap" + (store.micBlocked().show ? " show" : "") }, () => store.micBlocked().msg),
    // UPPER LID of the EYE — 7 controls arched over the orb (order L→R, CENTRE = ⏻ at the apex, outer icons dive
    // to the corners to meet the ECG's lower lid): ⏰ · 🧠 · 🔊 · ⏻ · 📝 · ☾ · 🤖. BLUE = on/open, GREY = off.
    h("div", { class: "orbctl" },
      h("button", {
        // 2026-08-09: relocated from CameraUnit (now hidden/archived) — same session.toggleMic()/store.micMuted()
        // seam, just a different button. ON (blue) = mic live, like the speaker's on/off language.
        class: () => "orbic" + (store.micMuted() ? " off" : " on"),
        title: () => (store.micMuted() ? t("camera.mic_unmute") : t("camera.mic_mute")),
        onClick: () => { session.toggleMic(); api.uiEvent("orb:mic", { state: store.micMuted() ? "muted" : "unmuted" }); },
      }, raw(MIC_ICON)),
      h("button", {
        class: () => "orbic" + (store.memOpen() ? " on" : " off"),
        title: () => t("orb.memory"),
        onClick: () => { const v = !store.memOpen(); store.setMemOpen(v); api.uiEvent("orb:memory", { state: v ? "open" : "close" }); },
      }, raw(MEM_ICON)),
      h("button", {
        class: () => "orbic" + (store.botMuted() ? " off" : " on"),
        title: () => store.botMuted() ? t("orb.speaker_muted") : t("orb.speaker_unmuted"),
        onClick: () => { session.toggleBotMute(); api.uiEvent("orb:speaker", { state: store.botMuted() ? "muted" : "unmuted" }); },
      }, () => raw(store.botMuted() ? SPK_OFF : SPK_ON)),
      h("button", {
        class: () => "orbic" + (store.powerOff() ? " off" : " on"),
        title: () => store.powerOff() ? t("orb.power_off") : t("orb.power_on"),
        onClick: () => {
          const off = !store.powerOff();
          store.setPowerOff(off);
          if (off) {
            // V2-066 (2026-07-24, petición explícita del operador tras un fallo real: "el botón principal tiene
            // que bloquear TODO — pausar procesos de desarrollo, parar el micrófono, parar el altavoz, detenerlo
            // todo"). `session.stop()` YA corta el micro (para los tracks reales de MediaStream, no solo el
            // icono) y el altavoz (pausa+desengancha <audio>) — pero lo hace de forma IMPLÍCITA, como parte de
            // desmontar la sesión entera. Se fuerzan TAMBIÉN los signals de mic/altavoz explícitamente aquí,
            // en defensa: si algún día `stop()` cambia y dejar de tocarlos, el candado de ⏻ no depende de ello.
            try { session.stop(); } catch (_) {}
            // Fin de la SESIÓN DE TRABAJO para observabilidad (2026-08-09): ⏻ es, junto con cerrar la pestaña,
            // el único gesto que significa «he terminado». Un `stop()` por reconexión NO cierra sesión — si lo
            // hiciera, un bache de red partiría en dos lo que el operador vive como una sola tarde de trabajo.
            api.obsSessionEnd("power_off");
            store.setMicMuted(true); localStorage.setItem("hb_mic_muted", "1");
            store.setBotMuted(true); localStorage.setItem("hb_bot_muted", "1");
            // Bug real 2026-07-23 (reporte del operador): apagar dejaba el pulso del ECG latiendo y los
            // subtítulos clavados. El ECG se autogenera latidos LOCALES mientras `store.tasks()` tenga algo sin
            // terminar (lib/ecg.js::activeLoad) — la reconciliación contra la verdad del server (GET /api/tasks)
            // solo corre al (re)conectar SSE (sse.js::es.onopen); si un `task end` se perdió en algún hueco de
            // reconexión, el chip huérfano se queda para SIEMPRE hasta la próxima reconexión — que con la voz
            // apagada nunca llega. Apagar debe dejar todo asentado: reconcilia aquí, aunque la SSE ya esté cerrada
            // (fetchTasks es un fetch aparte, no depende de ella).
            try { store.fetchTasks(); } catch (_) {}
            // V2-065 (petición del operador): ⏻ para TODO, pero PAUSA — no mata como Reset. Congela los Brain
            // Workers vivos (SIGSTOP, reversible) para que sigan EXACTAMENTE donde estaban al volver a encender.
            api.workersPause().then(() => store.fetchTasks());
          } else {
            // Simétrico: el mute que ⏻ impuso al apagar (arriba) se deshace al volver a encender — si el
            // operador quiere mic/altavoz mudos DE FORMA INDEPENDIENTE, ya tiene sus propios botones para eso.
            store.setMicMuted(false); localStorage.setItem("hb_mic_muted", "0");
            store.setBotMuted(false); localStorage.setItem("hb_bot_muted", "0");
            try { session.start(); } catch (_) {}
            api.workersResume().then(() => store.fetchTasks());
          }
          api.uiEvent("orb:power", { state: off ? "off" : "on" });
        },
      }, raw(PWR_ICON)),
      h("button", {
        class: () => "orbic" + (store.captionsOn() ? " on" : " off"),
        title: () => store.captionsOn() ? t("orb.captions_hide") : t("orb.captions_show"),
        onClick: () => { const v = store.toggleCaptions(); api.uiEvent("orb:captions", { state: v ? "on" : "off" }); },
      }, raw(CAP_ICON)),
      h("button", {
        // 2026-08-09: relocated from CameraUnit (now hidden/archived) — opens the SAME chat panel the old ⏰
        // cron shortcut used to jump into (crons live inside its 3rd tab; no separate cron icon any more).
        class: () => "orbic" + (store.chatOpen() ? " on" : " off"),
        title: () => t("camera.chat_title"),
        onClick: () => { const v = !store.chatOpen(); store.setChatOpen(v); api.uiEvent("orb:chat", { state: v ? "open" : "close" }); },
      }, raw(CHAT_ICON)),
      h("button", {
        class: () => "orbic" + (wakeOn() ? " on" : " off"),
        title: () => wakeOn() ? t("orb.wake_on") : t("orb.wake_off"),
        onClick: () => { toggleWake(); api.uiEvent("orb:attention", { state: wakeOn() ? "wakeword" : "always" }); },
      }, raw(BOT_ICON)),
    ),
    // orb + its overlays in a RELATIVE box: the caption is ABSOLUTE, anchored above the orb (bottom:100%), so it
    // grows UPWARD as lines crawl in — the orb itself never moves, and the text stays centred on it.
    h("div", { class: "orbcore" },
      // live captions: zaelar's speech crawls up from the orb (teleprompter): the first line fades in near the orb,
      // new lines push the stack up smoothly and the top line fades out — max 3 lines. Blurred dark scrim behind.
      h("div", { class: "orbcap", ref: el => (capEl = el) },
        h("div", { class: "orbcap-inner", ref: el => (capInnerEl = el) }),
      ),
      h("canvas", { id: "orb", class: () => store.botMuted() ? "muted" : "", ref: el => (orbEl = el),
                    title: () => t("orb.drag") }),
      h("div", { class: () => "micblock" + (store.micBlocked().show ? " show" : "") }, h("span", { class: "ring" })),
    ),
    // ELECTROCARDIOGRAM under the orb — zaelar's REAL heartbeat: a QRS per orchestrator loop.tick (~1 Hz at rest),
    // racing when there are background tasks / FlashBrain turns. Driven by lib/ecg.js off store.pulse. Flat = no
    // real pulse arriving (honest). pointer-events:none so it never steals the orb's drag.
    h("canvas", { class: "orbecg", ref: el => (ecgEl = el), "aria-hidden": "true" }),
  );

  makeDraggable(wrapEl, orbEl, "hb_pos_orb", "bl");   // drag the orb to move it (no click action any more)
  startEcg(ecgEl);                                    // start the heartbeat monitor (its own rAF; reads store.pulse)

  // ---- live-caption crawl, driven by LiveKit's AUDIO-SYNCED transcription (session-lk.js → store.captionSeg).
  // The spoken text arrives incrementally, paced to the voice. We wrap it into short lines; as the text grows,
  // new lines crawl in from the orb (teleprompter) and push the stack up — the top line fades out, max 3 shown.
  // No timers/guessing: the text advances exactly as it's heard. LIVE only; the chat wall keeps the history.
  const MAXCHARS = 42, MAXLINES = 3;
  let committedLines = [], curId = null, activeText = "", addedLines = 0;   // per-utterance streaming state
  let lineDivs = [], lastDiv = null, hideTimer = null, fresh = true, lastSeq = 0;

  const wrapText = (text) => {
    const words = (text || "").trim().split(/\s+/).filter(Boolean);
    const lines = []; let cur = "";
    for (const w of words) {
      if (!cur) cur = w;
      else if ((cur + " " + w).length <= MAXCHARS) cur += " " + w;
      else { lines.push(cur); cur = w; }
    }
    if (cur) lines.push(cur);
    return lines;
  };

  // Bug real 2026-07-23 (reporte del operador): con el ChatWall ABIERTO toda la conversación va por texto ahí —
  // los subtítulos sobre el orbe son EXCLUSIVOS del modo voz (ChatWall cerrado) y deben respetar el 📝 solo en ese
  // modo. Faltaba el gate `!store.chatOpen()`: el crawl seguía apareciendo sobre el orbe aunque el chat estuviera
  // abierto, sin importar el estado del icono de subtítulos.
  const showCap = (on) => { if (capEl) capEl.classList.toggle("show", on && store.captionsOn() && !store.chatOpen()); };
  const resetState = () => { committedLines = []; curId = null; activeText = ""; addedLines = 0; lastDiv = null; };
  const clearLines = () => { if (capInnerEl) capInnerEl.replaceChildren(); lineDivs = []; };
  const hideNow = () => { clearTimeout(hideTimer); hideTimer = null; showCap(false); clearLines(); resetState(); fresh = true; };
  const scheduleHide = () => { clearTimeout(hideTimer); hideTimer = setTimeout(hideNow, 2400); };

  const addLine = (text) => {
    if (!capInnerEl) return null;
    const div = document.createElement("div");
    div.className = "cl"; div.textContent = text;
    capInnerEl.appendChild(div);
    lineDivs.push(div);
    requestAnimationFrame(() => div.classList.add("in"));   // collapsed+below → full: grows from the orb, pushes up
    if (lineDivs.length > MAXLINES) {                        // drop the top line with a fade-out
      const top = lineDivs.shift();
      top.classList.remove("in"); top.classList.add("out");
      setTimeout(() => { if (top.parentNode) top.remove(); }, 500);
    }
    return div;
  };

  // Grow the crawl to match the spoken-so-far text = fixed committed lines + the active segment's wrapped lines.
  // Both are prefix-stable (greedy wrap), so we only ever APPEND a div per new line and keep the in-progress last
  // line's text in sync — no earlier line ever needs rewriting.
  const feed = () => {
    const lines = committedLines.concat(wrapText(activeText));
    if (!lines.length) return;
    if (lastDiv && addedLines > 0) lastDiv.textContent = lines[addedLines - 1] ?? lastDiv.textContent;  // commit prev tail
    for (let i = addedLines; i < lines.length; i++) { lastDiv = addLine(lines[i]); addedLines = i + 1; }
    lastDiv.textContent = lines[lines.length - 1];
  };

  createEffect(() => {                     // streaming transcription segment (synced to the voice)
    const seg = store.captionSeg();
    if (!seg || seg.seq === lastSeq) return;
    lastSeq = seg.seq;
    if (!store.captionsOn() || store.chatOpen()) return;
    clearTimeout(hideTimer); hideTimer = null;
    if (fresh) { clearLines(); resetState(); fresh = false; }
    if (seg.id !== curId) {                // a new segment began → freeze the previous one into committed lines
      if (activeText) committedLines.push(...wrapText(activeText));
      curId = seg.id; activeText = "";
    }
    activeText = seg.text;
    showCap(true);
    feed();
    if (seg.final) { committedLines.push(...wrapText(activeText)); activeText = ""; }
  });

  createEffect(() => {                     // zaelar stopped talking → hold briefly, then fade out
    if (store.botSpeaking()) { clearTimeout(hideTimer); hideTimer = null; return; }
    if (lineDivs.length || addedLines) scheduleHide();
  });

  createEffect(() => { if (!store.captionsOn()) hideNow(); });   // captions OFF → clear immediately
  createEffect(() => { if (store.chatOpen()) hideNow(); });      // chat wall opens → subtítulos son SOLO modo voz
  // Bug real 2026-07-23: el efecto de "zaelar dejó de hablar" (arriba) solo se dispara con una transición
  // true→false de botSpeaking — si ya estaba en false cuando se apaga, no hay transición que lo re-dispare y el
  // último subtítulo se queda clavado para siempre (la sesión se cierra, no llegan más segmentos que lo pisen).
  createEffect(() => { if (store.powerOff()) hideNow(); });      // apagar SIEMPRE limpia, sin depender de esa transición

  return wrap;
}
