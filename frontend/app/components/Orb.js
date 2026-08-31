// Orb — bottom-centre voice orb (zaelar's voice spectrum) = zaelar PERSONIFIED, the LIVE CAPTIONS that crawl up
// from it (Star-Wars style), the activity rail, the transient flash label, the 🚫 mic-blocked ring/caption, and
// — V2-039 “EL OJO” (operator 2026-07-17) — the whole cluster reads as an EYE: the icon arc above is the UPPER
// LID, the ECG arc below (lib/ecg.js) is the LOWER LID, the orb is the IRIS. Both arcs stretch so their tips
// nearly meet at the corners (canthi). SEVEN controls on the upper lid (L→R):
//   🎤 mic      → mute/unmute the OPERATOR'S OWN microphone input. MOVED here 2026-08-09 when the CameraUnit
//                 widget (its former home) was hidden/archived — same session.toggleMic()/store.micMuted() seam.
//   🧠 memory   → open the MEMORAnd MAP visualizer (state + short/long-term + concept graph, V2-014). BLUE while open.
//   🔊 speaker  → mute/unmute zaelar's voice OUTPUT (the agent keeps running: mic, brain and crons stay live).
//   ⏻ power    → CENTRE (apex). Explicit ON/OFF of the voice session — the ONE exception to always-on: while
//                 off (persisted hb_power_off) main.js does NOT auto-(re)connect; click again to come back.
//                 While OFF, the OTHER six controls read DISABLED (grey) too via lidClass(): a stopped agent can't
//                 use mic/speaker/captions, and live-blue icons over a stopped session used to look like an audio
//                 bug. Each control keeps its own state underneath and shows it again once power returns.
//   📝 captions → show/hide the live transcript crawling above the orb (history always stays in the chat wall).
//   💬 chat     → open the chat panel (Chat/Processes/Crons/Clusters tabs — crons live INSIDE it, no separate
//                 cron icon any more). MOVED here 2026-08-09, same slot the ⏰ cron shortcut used to occupy;
//                 replaces both that shortcut AND CameraUnit's own chat button (archived along with it).
//   🤖 robot    → attention gate (V2-016). OFF (grey) = `always`; ON (blue) = `wakeword` ("zaelar"/"harvis").
//                 Toggles attention_mode LIVE via the SAME settings seam the ⚙ uses (POST /api/settings).
// All controls are frameless icons: BLUE when ON/open, pale GREEN when OFF/closed. The lid arc is drawn by CSS
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

  // ⏻ STOPPED dims the whole lid (operator request): a stopped agent can't use mic/speaker/captions — and
  // when the mic/speaker icons kept reading ON (blue) over a stopped session, the operator mistook a stopped
  // agent for a broken mic. Now, while ⏻ is OFF, the OTHER six controls all read as DISABLED (grey .off) whatever
  // their own signal says, so there's no doubt the agent is stopped. The ⏻ icon itself already reads "off", and
  // clicking it is how you bring everything back. Visual only: each control keeps its real state underneath and
  // reflects it again the moment power returns. (Reactive: reads powerOff() inside the class effect → repaints on
  // toggle, same as every other icon here.)
  // 2026-08-10: the condition was `!store.powerOff()` — the persisted INTENT. It did not cover the case that really
  // caused damage: `powerOff=false` with the session DOWN painted the mic and speaker blue over a dead agent.
  // Now it depends on `agentLive()` (store.js), which is reality: if the agent is not alive, NO icon can
  // read as on, regardless of its own signal. Visually, each control keeps its state underneath and shows it again
  // as soon as the agent is alive.
  const lidClass = (on) => "orbic" + (on && store.agentLive() ? " on" : " off");

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
    // to the corners to meet the ECG's lower lid): ⏰ · 🧠 · 🔊 · ⏻ · 📝 · ☾ · 🤖. BLUE = on/open, GREEN = off.
    h("div", { class: "orbctl" },
      h("button", {
        // 2026-08-09: relocated from CameraUnit (now hidden/archived) — same session.toggleMic()/store.micMuted()
        // seam, just a different button. ON (blue) = mic live, like the speaker's on/off language.
        //
        // VU METER (2026-08-10, operator request): “I want to be sure you're listening to me when I speak, and since
        // we have no meter on screen, I would like the microphone icon to blink and become a little larger and smaller
        // as it detects my voice.” In other words, the icon itself IS the meter, just as the orb grows when zaelar speaks.
        // It scales with the mic's REAL level (store.micLevel, RMS 0..1) through a CSS variable, so the animation costs
        // no re-render: it only changes a custom property. With the mic muted or the agent stopped there is no effect —
        // because there is no level: the meter can move only when the system is actually listening.
        class: () => lidClass(!store.micMuted()) + (store.agentLive() && !store.micMuted() ? " vu" : ""),
        style: { "--vu": () => (store.agentLive() && !store.micMuted() ? String(Math.min(1, store.micLevel() * 6)) : "0") },
        title: () => (store.micMuted() ? t("camera.mic_unmute") : t("camera.mic_mute")),
        onClick: () => { session.toggleMic(); api.uiEvent("orb:mic", { state: store.micMuted() ? "muted" : "unmuted" }); },
      }, raw(MIC_ICON)),
      h("button", {
        class: () => lidClass(store.memOpen()),
        title: () => t("orb.memory"),
        onClick: () => { const v = !store.memOpen(); store.setMemOpen(v); api.uiEvent("orb:memory", { state: v ? "open" : "close" }); },
      }, raw(MEM_ICON)),
      h("button", {
        class: () => lidClass(!store.botMuted()),
        title: () => store.botMuted() ? t("orb.speaker_muted") : t("orb.speaker_unmuted"),
        onClick: () => { session.toggleBotMute(); api.uiEvent("orb:speaker", { state: store.botMuted() ? "muted" : "unmuted" }); },
      }, () => raw(store.botMuted() ? SPK_OFF : SPK_ON)),
      h("button", {
        // The ⏻ is the ONLY icon that can never lie: it is what the operator looks at to know whether someone is
        // al otro lado. Pinta the CUATRO estados reales (store.agentState), no the flag persistido:
        //   live → blue · starting → “starting up” · off → grey (stopped manually) · stalled → WARNING.
        // `stalled` (“it should be on, but it isn't”) is the state that did not exist before: with it, a fallen agent
        // looks fallen instead of appearing operational.
        class: () => "orbic pwr-" + store.agentState() + (store.agentLive() ? " on" : " off"),
        title: () => t("orb.power_" + store.agentState()),
        onClick: () => {
          const off = !store.powerOff();
          // Stamp the command BEFORE applying it: from here on, any server reconciliation that went to fetch the
          // state before this instant is holding a stale snapshot and must stay quiet (see store.js and the
          // seeding in main.js). Without this, a cold start tore down the session just asked for.
          store.markPowerCommand();
          store.setPowerOff(off);
          if (off) {
            // V2-066 (2026-07-24, explicit operator request after a real failure: "the main button must block
            // EVERYTHING — pause development processes, stop the microphone, stop the speaker, stop everything").
            // `session.stop()` ALREADY cuts the mic (stops the real MediaStream tracks, not just the icon) and the
            // speaker (pauses+detaches <audio>) — but it does so IMPLICITLY, as part of tearing down the whole session.
            // The mic/speaker signals are ALSO forced explicitly here as a safeguard: if `stop()` ever changes and
            // stops touching them, the ⏻ lock does not depend on it.
            try { session.stop(); } catch (_) {}
            // End of the WORK SESSION for observability (2026-08-09): ⏻ is, along with closing the tab, the only
            // gesture that means “I'm done.” A `stop()` caused by reconnection does NOT close the session — if it did,
            // a network hiccup would split in two what the operator experiences as one afternoon of work.
            api.obsSessionEnd("power_off");
            store.setMicMuted(true); localStorage.setItem("hb_mic_muted", "1");
            store.setBotMuted(true); localStorage.setItem("hb_bot_muted", "1");
            // Real bug 2026-07-23 (operator report): powering off left the ECG pulse beating and the captions stuck.
            // The ECG locally generates beats while `store.tasks()` has something unfinished (lib/ecg.js::activeLoad)
            // — reconciliation against the server's truth (GET /api/tasks) only runs when reconnecting SSE
            // (sse.js::es.onopen); if a `task end` was lost during a reconnection gap, the orphaned chip remains
            // FOREVER until the next reconnection — which never arrives with the voice off. Powering off must settle
            // everything: reconcile here, even though SSE is already closed (fetchTasks is a separate fetch and does
            // not depend on it).
            try { store.fetchTasks(); } catch (_) {}
            // V2-065 (operator request): ⏻ stops EVERYTHING, but PAUSES — it does not kill like Reset. Freeze the Brain
            // Workers vivos (SIGSTOP, reversible) for that sigan EXACTAMENTE where estaban al volver a encender.
            // V2-092: the command goes to the server's GLOBAL SWITCH, which does that and also suspends producing
            // widgets (the video that kept playing over a stopped agent), cuts background cycles and crons, and
            // blocks new work. The server saves the state → reloading the page no longer resurrects anything.
            api.runStop().then(() => store.fetchTasks());
          } else {
            // Symmetrically, the mute imposed by ⏻ when powering off (above) is undone when powering on — if the
            // operator wants the mic/speaker muted INDEPENDENTLY, they have their own buttons for that.
            store.setMicMuted(false); localStorage.setItem("hb_mic_muted", "0");
            store.setBotMuted(false); localStorage.setItem("hb_bot_muted", "0");
            // ORDER: the SERVER first, the voice session AFTER (2026-08-31, operator: "when I press the start button
            // it stays blinking yellow… if I refresh the page, everything starts automatically"). `session.start()` opens with a ⏻ gate against the server's truth
            // (`GET /api/run`, session-lk.js) — so starting it BEFORE `runStart()` had landed made that gate read
            // the state from before this very click, abort the startup and set `powerOff` back to true. What then
            // brought it up was the SSE `run` event undoing that flag plus the operator's NEXT pointer landing on
            // `ensureVoice()` — which is exactly why it looked like "a minute or two" and why a RELOAD was
            // instant: by then the server already said RUNNING and the gate let it through.
            // Turning on CONTINUES frozen work (SIGCONT) but does NOT resume widgets: putting the music or the
            // video back on is the operator's gesture, not a consequence of powering on (deliberate asymmetry,
            // see nucleo/runstate.py).
            api.runStart().then(() => {
              store.fetchTasks();
              try { session.start(); } catch (_) {}
            });
          }
          api.uiEvent("orb:power", { state: off ? "off" : "on" });
        },
      }, raw(PWR_ICON)),
      h("button", {
        class: () => lidClass(store.captionsOn()),
        title: () => store.captionsOn() ? t("orb.captions_hide") : t("orb.captions_show"),
        onClick: () => { const v = store.toggleCaptions(); api.uiEvent("orb:captions", { state: v ? "on" : "off" }); },
      }, raw(CAP_ICON)),
      h("button", {
        // 2026-08-09: relocated from CameraUnit (now hidden/archived) — opens the SAME chat panel the old ⏰
        // cron shortcut used to jump into (crons live inside its 3rd tab; no separate cron icon any more).
        class: () => lidClass(store.chatOpen()),
        title: () => t("camera.chat_title"),
        onClick: () => { const v = !store.chatOpen(); store.setChatOpen(v); api.uiEvent("orb:chat", { state: v ? "open" : "close" }); },
      }, raw(CHAT_ICON)),
      h("button", {
        class: () => lidClass(wakeOn()),
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
      // `frozen` (2026-08-10): with the agent stopped, the orb turns off and remains STILL. It is the piece that most
      // “personifies” zaelar, so seeing it ripple with the agent stopped is the most misleading signal on the whole
      // screen. The visualizer also stops advancing its phase, so it is not merely grey: it does not move.
      h("canvas", { id: "orb",
                    class: () => (store.botMuted() ? "muted" : "") + (store.agentLive() ? "" : " frozen"),
                    ref: el => (orbEl = el), title: () => t("orb.drag") }),
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

  // Real bug 2026-07-23 (operator report): with the ChatWall OPEN, the entire conversation is shown there as text —
  // captions over the orb are EXCLUSIVE to voice mode (ChatWall closed) and must honor 📝 only in that mode.
  // The `!store.chatOpen()` gate was missing: the crawl kept appearing over the orb even when chat was open,
  // regardless of the captions icon's state.
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
  createEffect(() => { if (store.chatOpen()) hideNow(); });      // chat wall opens → captions are ONLY for voice mode
  // Real bug 2026-07-23: the "zaelar stopped talking" effect (above) only fires on a true→false transition of
  // botSpeaking — if it was already false when powering off, there is no transition to trigger it again, and the last
  // caption remains stuck forever (the session closes, so no more segments arrive to overwrite it).
  createEffect(() => { if (store.powerOff()) hideNow(); });      // powering off ALWAYS clears captions, regardless of that transition

  return wrap;
}
