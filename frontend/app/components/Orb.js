// Orb — bottom-centre voice orb (zaelar's voice spectrum) = zaelar PERSONIFIED, the LIVE CAPTIONS that crawl up
// from it (Star-Wars style), the activity rail, the transient flash label, the 🚫 mic-blocked ring/caption, and
// — V2-039 “EL OJO” (operator 2026-07-17) — the whole cluster reads as an EYE: the icon arc above is the UPPER
// LID, the ECG arc below (lib/ecg.js) is the LOWER LID, the orb is the IRIS. Both arcs stretch so their tips
// nearly meet at the corners (canthi). SEVEN controls on the upper lid (L→R):
//   🎤 mic      → mute/unmute the OPERATOR'S OWN microphone input. MOVED here 2026-08-09 when the CameraUnit
//                 widget (its former home) was hidden/archived — same session.toggleMic()/store.micMuted() seam.
//   ⇩ to-bar    → V2-623: LEFT CORNER — sends the orb into the bottom system bar (small orb at its centre, eye
//                 chrome hidden); the bar's own centre button brings it back. The 🧠 memory control that lived
//                 here moved to the TopBar the same pass (operator, 2026-09-08).
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
import * as mic from "../services/mic.js?v=1";
import * as power from "../services/power.js?v=1";
import { makeDraggable, resetDraggable } from "../lib/draggable.js?v=2";
import { startEcg } from "../lib/ecg.js?v=2";
import { t } from "../core/i18n.js?v=1";
import { problemTitleKey } from "../services/device-health.js?v=1";

// Inline SVGs (self-contained, currentColor). Mic + memory + speaker on/off + power + captions + chat + robot.
const MIC_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/></svg>`;
// V2-648 — a STOPPED mic is CROSSED OUT, exactly like the speaker's own off face. Operator, 2026-09-10:
// «cuando el micro está desactivado, aparte de que se quede en gris, quiero que se vea un icono de micro
// tachado, porque si no se aprecia poco». Grey alone was carrying the whole message, and grey is what a
// disabled control looks like anyway — the SHAPE has to say it, so it reads without comparing brightnesses.
// The slash keeps its own class so a test can measure that it actually RENDERS (the 4.19 lesson) rather
// than trusting that the right string was chosen.
const MIC_OFF = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/><path class="mic-slash" d="m3.5 3.5 17 17"/></svg>`;
// V2-623 — send the orb into the bottom system bar: an orb dropping onto a bar. The 🧠 memory icon that used
// to sit on this lid moved to the TopBar the same pass (operator: «quita el icono de la memoria del orbe»).
const TOBAR_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v8"/><path d="m8 8 4 4 4-4"/><rect x="3" y="16" width="18" height="5" rx="2"/></svg>`;
const SPK_ON  = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M18.5 5.5a9 9 0 0 1 0 13"/></svg>`;
const SPK_OFF = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="m22 9-6 6"/><path d="m16 9 6 6"/></svg>`;
const CAP_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="3"/><path d="M7 10h5"/><path d="M7 14h9"/></svg>`;
const CHAT_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.4 9.06 9.06 0 0 1-4-.9L3 21l1.9-4.5a8.38 8.38 0 0 1-.9-4A8.5 8.5 0 0 1 12.5 4 8.38 8.38 0 0 1 21 11.5z"/></svg>`;
const BOT_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect x="4" y="8" width="16" height="12" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M9 13v2"/><path d="M15 13v2"/></svg>`;
const PWR_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.77.04"/></svg>`;

export function Orb() {
  let wrapEl, orbEl, capEl, capInnerEl, ecgEl, micblockEl;

  // ---- attention gate toggle (V2-016 + 2026-09-09 "Modo Nombre"). ON = `smart` (wake-word OR an active
  // conversation window — say the name once, keep talking through short pauses; NOT raw `wakeword`, which
  // re-demands it every utterance with no window: measured live, that is exactly what made a rename look
  // "worked twice and then stopped"). OFF = always (listens+answers to everything, default).
  // store.attentionMode/assistantName mirror config/settings.json — read once here (GET /api/settings), kept
  // live afterwards by the `ui`/`orb:attention` + `orb:name` SSE events (sse.js) whichever side changes them,
  // button OR voice ("activa el modo nombre" — nucleo/flash/identity_actions.py). Toggling writes LIVE via the
  // same /api/settings seam the ⚙ uses (attention_mode is "live" — voice/attention.py::mode() reads
  // ZAELAR_ATTENTION each turn, no reconnect needed).
  const wakeOn = () => store.attentionMode() === "smart" || store.attentionMode() === "wakeword";
  api.getSettings()
    .then(cfg => {
      const knob = (cfg.knobs || []).find(k => k.key === "attention_mode");
      if (knob) store.setAttentionMode(knob.value === "wakeword" ? "smart" : knob.value);
      if (cfg.assistant_name) store.setAssistantName(cfg.assistant_name);
    })
    .catch(() => {});
  const toggleWake = () => {
    const prev = store.attentionMode();
    const next = wakeOn() ? "always" : "smart";
    store.setAttentionMode(next);                               // optimistic; reflects immediately
    api.saveSettings({ attention_mode: next }).catch(() => store.setAttentionMode(prev));   // revert on failure
    // V2-749 — SAY THE WORD OUT LOUD, WHERE HE IS LOOKING. Turning this on changes whether the agent answers
    // at all, and until now the only place that said so was a tooltip nobody hovers after clicking. The
    // operator: «cuando el usuario lo clique, podría aparecer en el sitio de los subtítulos… una nota, quizás
    // en otro color, que dijera durante tres segundos: para activar, di la palabra, y ponemos ahí la palabra
    // entre comillas». It carries the CURRENT name, because that is the thing he cannot know — he renamed it
    // by voice and the word changed with it (V2-747).
    showWakeHint(next === "always" ? t("orb.wake_hint_off")
                                   : t("orb.wake_hint_on", { name: store.assistantName() }));
  };

  // The note lives where the subtitles live and expires on its own. Deliberately NOT a line of the crawl:
  // the crawl is a transcript of what was SAID, and writing our own notice into it would make the agent
  // appear to have spoken it.
  const [wakeHint, setWakeHint] = createSignal("");
  let _hintT = null;
  const showWakeHint = (text) => {
    setWakeHint(String(text || ""));
    clearTimeout(_hintT);
    _hintT = setTimeout(() => setWakeHint(""), 3000);
  };

  // ⏻ STOPPED dims the whole lid (operator request): a stopped agent can't use mic/speaker/captions — and
  // when the mic/speaker icons kept reading ON (blue) over a stopped session, the operator mistook a stopped
  // agent for a broken mic. Now, while ⏻ is OFF, the OTHER six controls all read as DISABLED (grey .off) whatever
  // their own signal says, so there's no doubt the agent is stopped. The ⏻ icon itself already reads "off", and
  // clicking it is how you bring everything back. Visual only: each control keeps its real state underneath and
  // reflects it again the moment power returns. (Reactive: reads powerOff() inside the class effect → repaints on
  // toggle, same as every other icon here.)
  // 2026-08-10: it reads `agentLive()` (reality), not `powerOff()` (the persisted intent, which painted the mic and
  // speaker lit over a DOWN session): if the agent is not alive, no icon reads as on, whatever its own signal.
  const lidClass = (on) => "orbic" + (on && store.agentLive() ? " on" : " off");
  // V2-792 §9 (operator, 2026-10-25): GREY = off or closed, LILAC = on or open. The two DEVICE controls (mic,
  // speaker) are lilac only while really live on THIS screen — `lidClass` above, since a stopped agent or a voice
  // held elsewhere hears and says nothing here. A SECTION (the chat) or a SETTING (captions, wake word) shows its
  // own open/on state whatever the agent is doing: the chat is open or it is not.
  const secClass = (on) => "orbic" + (on ? " on" : " off");
  // V2-831 T-18: GREY `wait` (full strength, no slash) while the parked tap sends nothing to the STT; else lidClass.
  const waiting = () => !!(session.tapParked && session.tapParked());
  const devClass = (on) => (on && store.agentLive() && waiting() ? "orbic wait" : lidClass(on));
  // The ⏻ means POWER and nothing else: grey only when the agent is stopped. «Voice on another screen» is not
  // stopped (that face is what made the operator stop everything, 2026-10-25); it is shown on the orb.
  const pwrState = () => (store.agentState() === "remote" ? "live" : store.agentState());

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
    // to the corners to meet the ECG's lower lid): ⇩ · 🎤 · 🔊 · ⏻ · 📝 · 💬 · 🤖. BLUE = on/open, GREEN = off.
    // V2-623: the 🧠 memory control moved to the TopBar; the LEFT CORNER slot is the swap that sends the orb
    // into the bottom bar («en una esquina de los iconos del orbe») — the slot count stays 7, so the arc's
    // nth-child geometry is untouched and ⏻ keeps the apex.
    h("div", { class: "orbctl" },
      h("button", { "data-ctl": "tobar",
        class: () => lidClass(false),
        title: () => t("orb.to_bar"),
        onClick: () => { store.setOrbDock("bar"); api.uiEvent("orb:dock", { where: "bar" }); },
      }, raw(TOBAR_ICON)),
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
        "data-ctl": "mic",
        // V2-788: red when the DEVICE has a problem (store.micHealth — a deliberate mute is not one).
        class: () => devClass(!store.micMuted()) + (store.agentLive() && !store.micMuted() && !waiting() ? " vu" : "")
                     + (store.micHealth().ok ? "" : " problem"),
        style: { "--vu": () => (store.agentLive() && !store.micMuted() ? String(Math.min(1, store.micLevel() * 6)) : "0") },
        title: () => (!store.micHealth().ok ? t(problemTitleKey("mic", store.micHealth().reason))
                      : store.micMuted() ? t("camera.mic_unmute") : t("camera.mic_mute")),
        // Opening the mic by hand brings the voice to this surface (session.openMicHere); closing it is local.
        onClick: () => {
          if (store.micMuted() && session.openMicHere) session.openMicHere("orb");
          else mic.toggle("orb");
          api.uiEvent("orb:mic", { state: store.micMuted() ? "muted" : "unmuted" });
        },
      }, () => raw(store.micMuted() ? MIC_OFF : MIC_ICON)),
      h("button", { "data-ctl": "spk",
        class: () => devClass(!store.botMuted()) + (store.spkHealth().ok ? "" : " problem"),
        title: () => !store.spkHealth().ok ? t(problemTitleKey("spk", store.spkHealth().reason))
                   : store.botMuted() ? t("orb.speaker_muted") : t("orb.speaker_unmuted"),
        // V2-788: a red speaker is a click to RECOVER playback (inside the gesture), not to mute it — muting a
        // speaker the operator cannot hear would just hide the fault.
        onClick: () => {
          if (!store.spkHealth().ok) { try { session.unlockAudio && session.unlockAudio(); } catch (_) {}
                                       api.uiEvent("orb:speaker", { state: "recover", reason: store.spkHealth().reason }); return; }
          if (store.botMuted() && session.openSpeakerHere) session.openSpeakerHere("orb");
          else session.toggleBotMute();
          api.uiEvent("orb:speaker", { state: store.botMuted() ? "muted" : "unmuted" });
        },
      }, () => raw(store.botMuted() ? SPK_OFF : SPK_ON)),
      h("button", {
        // The ⏻ is the ONLY icon that can never lie: it is what the operator looks at to know whether someone is
        // al otro lado. Pinta the CUATRO estados reales (store.agentState), no the flag persistido:
        //   live → blue · starting → “starting up” · off → grey (stopped manually) · stalled → WARNING.
        // `stalled` (“it should be on, but it isn't”) is the state that did not exist before: with it, a fallen agent
        // looks fallen instead of appearing operational.
        "data-ctl": "pwr",
        class: () => "orbic pwr-" + pwrState() + (pwrState() === "live" ? " on" : " off"),
        title: () => t("orb.power_" + store.agentState()),
        // V2-792 §9 — the body moved to `services/power.js`, the ONE door both shells switch the agent through.
        onClick: () => power.togglePower("orb"),
      }, raw(PWR_ICON)),
      h("button", { "data-ctl": "cap",
        class: () => secClass(store.captionsOn()),
        title: () => store.captionsOn() ? t("orb.captions_hide") : t("orb.captions_show"),
        onClick: () => { const v = store.toggleCaptions(); api.uiEvent("orb:captions", { state: v ? "on" : "off" }); },
      }, raw(CAP_ICON)),
      h("button", {
        // 2026-08-09: relocated from CameraUnit (now hidden/archived) — opens the SAME chat panel the old ⏰
        // cron shortcut used to jump into (crons live inside its 3rd tab; no separate cron icon any more).
        "data-ctl": "chat",
        class: () => secClass(store.chatOpen()),
        title: () => t("camera.chat_title"),
        // From the orb the wall FLOATS — unless it is already docked, which the wall respects (operator, 2026-10-04).
        onClick: () => { const v = !store.chatOpen(); if (v) store.openChatFrom("orb"); else store.setChatOpen(false); api.uiEvent("orb:chat", { state: v ? "open" : "close" }); },
      }, raw(CHAT_ICON)),
      h("button", { "data-ctl": "bot",
        class: () => secClass(wakeOn()),
        // The tooltip answers the one question this button raises — «what do I have to say?» — with the word
        // ITSELF, in the operator's language and with today's name in it (V2-749).
        title: () => wakeOn() ? t("orb.wake_on", { name: store.assistantName() }) : t("orb.wake_off", { name: store.assistantName() }),
        onClick: () => { toggleWake(); api.uiEvent("orb:attention", { state: store.attentionMode() }); },
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
      // V2-749 — the wake-word note, in the captions' own place and in its own colour so it never reads as
      // something the agent said.
      h("div", { class: () => "orbhint" + (wakeHint() ? " show" : "") }, () => wakeHint()),
      // `frozen` (2026-08-10): with the agent stopped, the orb turns off and remains STILL. It is the piece that most
      // “personifies” zaelar, so seeing it ripple with the agent stopped is the most misleading signal on the whole
      // screen. The visualizer also stops advancing its phase, so it is not merely grey: it does not move.
      // V2-648: the SPEAKER is gone from here. The orb's colour is the LISTENING signal (warm = «te escucho»),
      // and dimming it because zaelar's own voice is silenced answered a different question on the same
      // surface — the operator read the desaturated orange as «no me escucha». `frozen` stays: a stopped
      // agent is not listening either, and it must look and be still.
      h("canvas", { id: "orb",
                    class: () => (store.agentLive() ? "" : "frozen"),
                    ref: el => (orbEl = el), title: () => t("orb.drag") }),
      // V2-792 §9 — the voice is on ANOTHER screen: the grey orb wears the slashed mic, the phone's own look.
      h("div", { class: () => "orbsec" + (store.screenState() === "secondary" ? " show" : ""),
                 title: () => t("orb.centre_secondary"), "aria-hidden": "true" }, raw(MIC_OFF)),
      h("div", { class: () => "micblock" + (store.micBlocked().show ? " show" : ""), ref: el => (micblockEl = el) }, h("span", { class: "ring" })),
      // "te estoy escuchando" ring (2026-09-09): lights up the instant the attention gate judges a turn
      // DIRECTED at zaelar (voice/attention.py via nucleo.py's `emit("ambient", "👂 dirigido a zaelar", …)`) —
      // the operator's own ask: some visible proof he is heard, in EVERY mode (Modo Nombre or the default
      // always-on), not only once he has already started talking and hopes for the best.
    ),
    // ELECTROCARDIOGRAM under the orb — zaelar's REAL heartbeat: a QRS per orchestrator loop.tick (~1 Hz at rest),
    // racing when there are background tasks / FlashBrain turns. Driven by lib/ecg.js off store.pulse. Flat = no
    // real pulse arriving (honest). pointer-events:none so it never steals the orb's drag.
    h("canvas", { class: "orbecg", ref: el => (ecgEl = el), "aria-hidden": "true" }),
  );

  makeDraggable(wrapEl, orbEl, "hb_pos_orb", "bl");   // drag the orb to move it (no click action any more)

  // V2-623 — WHERE THE ORB LIVES. ONE canvas, ever (the 4.19 lesson: an orb canvas re-created inside a
  // conditional renders BLANK with no error) — "bar" REPARENTS this same #orb element into the bottom bar's
  // centre slot and hides the eye chrome via a body class (the #activity rail and the flash label stay
  // visible: a transient notice must not die with the eye); "eye" puts the canvas back in .orbcore before the
  // micblock ring. The bar may mount after us on a persisted "bar" boot, so the move retries on a frame until
  // its slot exists.
  // The lid's own controls FLANK the bar orb, three a side (operator, 2026-09-08: «el orbe tiene que estar
  // en el centro y a los lados los tres iconos a un lado y los tres al otro»): mic·spk·captions left,
  // robot·chat·(the bar's own swap) right — order fixed 2026-09-11 at the operator's request: immediately
  // right of the orb comes the wake-word/activation-mode toggle, then chat, then the swap that returns to
  // the eye. ⏻ does NOT travel: in bar mode the ORB IS THE SWITCH — the
  // slot button forwards its click to the real ⏻ (data-ctl="pwr"), the exact V2-124 mobile-dock pattern.
  // The buttons are MOVED, never rebuilt, so every handler/signal binding travels with its element.
  // The buttons may live in the document (after mount) or still inside the detached wrapEl (the very first
  // effect run happens before mounting) — check both, and NEVER hand append() a null: append(null) does not
  // throw, it prints the literal text "null" (seven of them beside the orb, operator screenshot 2026-09-09).
  const byCtl = (c) => document.querySelector(`[data-ctl="${c}"]`) || wrapEl.querySelector(`[data-ctl="${c}"]`);
  const ctls = (...ids) => ids.map(byCtl).filter(Boolean);
  let _dockRaf = 0;
  const applyOrbDock = () => {
    const mode = store.orbDock();
    document.body.classList.toggle("hb-orb-bar", mode === "bar");
    cancelAnimationFrame(_dockRaf);
    if (mode === "bar") {
      const slot = document.querySelector("#wrail .wr-orbslot");
      const l = document.querySelector("#wrail .wr-orbl");
      const r = document.querySelector("#wrail .wr-orbr");
      if (!slot || !l || !r) { _dockRaf = requestAnimationFrame(applyOrbDock); return; }
      if (orbEl.parentNode !== slot) slot.appendChild(orbEl);
      l.append(...ctls("mic", "spk", "cap"));
      r.prepend(...ctls("bot", "chat"));                 // the bar's .wr-swap stays last
    } else {
      const ctl = wrapEl.querySelector(".orbctl");
      // append() re-inserts in canonical lid order — the slot count stays 7 and ⏻ keeps the apex.
      if (ctl) ctl.append(...ctls("tobar", "mic", "spk", "pwr", "cap", "chat", "bot"));
      if (micblockEl && orbEl.nextSibling !== micblockEl) micblockEl.parentNode.insertBefore(orbEl, micblockEl);
    }
  };
  createEffect(applyOrbDock);

  // KEEP THE ORB IN THE SAME RELATIVE PLACE when a docked column changes the size of the visible area
  // (operator, 2026-09-07): «tienes que dejar el orbe visible… si estaba abajo y centrado, déjalo en la misma
  // posición relativa donde estaba, pero en el nuevo tamaño de la zona visible».
  //
  // Two cases, and only one of them needs JS. An orb he has never dragged is centred by CSS, which now centres
  // it on the DESK instead of the window — no code, nothing to keep in sync. An orb he HAS dragged carries an
  // inline `left` in viewport pixels (makeDraggable persists it), and that pixel is meaningless once the band
  // moves: it is remapped by the FRACTION of the band it sat at, which is what «misma posición relativa» means.
  // Clamped so it can never end up under the column or off the screen — «tienes que dejar el orbe visible».
  // The band is the DESK's own width, and the orb's inline `left` is already a desk pixel (it lives inside
  // #desk). So there is no viewport arithmetic here at all — only «which fraction of the desk was it at».
  const band = () => {
    const d = document.getElementById("desk");
    const r = d && d.getBoundingClientRect();
    return (r && r.width) ? r.width : innerWidth;
  };
  let lastW = band();
  const remapOrb = () => {
    const now = band(), prev = lastW;
    lastW = now;
    if (!wrapEl || !prev || !now) return;
    if (Math.abs(now - prev) < 1) return;
    const inline = parseFloat(wrapEl.style.left);
    if (!isFinite(inline)) return;                       // never dragged → CSS keeps it centred on the desk
    const w = wrapEl.offsetWidth || 0;
    const frac = (inline + w / 2) / prev;                // where in the band its CENTRE sat
    const left = Math.max(0, Math.min(frac * now - w / 2, now - w));
    wrapEl.style.left = Math.round(left) + "px";
    try { const p = JSON.parse(localStorage.getItem("hb_pos_orb") || "null");
          if (p) { p.left = Math.round(left); localStorage.setItem("hb_pos_orb", JSON.stringify(p)); } } catch (_) {}
  };
  // A frame later: the CSS inset lands on `#desk` in the same tick the event fires, and reading the band before
  // the browser has applied it measures the OLD desk and remaps to where it already was.
  const onCanvas = () => requestAnimationFrame(remapOrb);
  document.addEventListener("hb:canvas-resized", onCanvas);
  document.addEventListener("hb:rail-resized", onCanvas);
  addEventListener("resize", onCanvas);
  // RESET returns the orb to its birthplace (operator, 2026-09-07: «cuando se hace un reset, quiero que
  // el orbe vuelva a su posición inicial»). resetDraggable drops the dragged position — inline styles AND
  // `hb_pos_orb` — and `.orbwrap`'s own CSS centres it on the desk again. `lastW` re-reads the band so a
  // later dock/undock remaps from the fresh centre, not from the pre-reset geometry. The event comes from
  // `_clearCanvasAndLog()` (session-lk.js), the client-side deterministic reset path.
  document.addEventListener("hb:canvas-reset", () => {
    resetDraggable(wrapEl, "hb_pos_orb");
    lastW = band();
  });
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
