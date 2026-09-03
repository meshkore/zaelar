// ============================================================================
// mobile/app/main.js — ENTRY POINT OF THE MOBILE SHELL (V2-124).
//
// The mobile counterpart of app/main.js. It boots the SAME engine through the SAME services and the SAME store;
// what differs is the shape of the screen it builds. Read app/main.js for the desktop version — the two files are
// deliberately parallel, and every place they diverge is commented with why.
//
// WHAT IS SHARED (imported, never forked): core/store.js · core/reactive.js · core/dom.js · core/i18n.js and all of
// services/. One truth about the agent, two faces.
// WHAT IS NEW (this folder only): the Deck host, the bottom dock, the sheets, the CSS, the PWA plumbing.
//
// ORDER MATTERS, same as on the desktop: the deck wrapper must exist before the Deck is constructed, and the dock
// must be mounted before anything reads --dock-h.
// ============================================================================

import { h, mount, $ } from "../../app/core/dom.js?v=2";
import { createEffect } from "../../app/core/reactive.js?v=2";
import * as store from "../../app/core/store.js?v=2";
import * as session from "../../app/services/session.js?v=3";
import { openSSE } from "../../app/services/sse.js?v=4";
import * as api from "../../app/services/api.js?v=2";
import { startStatusPolling } from "../../app/services/status.js?v=2";
import { initTheme } from "../../app/services/theme.js?v=2";
import { initI18n } from "../../app/core/i18n.js?v=1";
import { submitChat } from "../../app/components/ChatWall.js?v=5";

import { Deck } from "./shell/Deck.js?v=1";
import { MOBILE_SURFACES } from "./shell/mobile-surfaces.js?v=1";

// ---- theme + language before mounting anything, so nothing flashes the wrong palette or the wrong words ----
initTheme();
initI18n();

// ---- the deck wrapper. ONE structural div, versus the desktop's #desk/.canvas/#wstage/#activity stack: there is
// nothing to place here, so there is nothing to build a coordinate system for. ----
const wrap = mount(h("div", { id: "zm-deck-wrap" }));
mount(h("div", { class: "zm-bg" }), wrap);                 // the canvas backdrop, purely decorative
const stage = mount(h("div", { id: "zm-stage" }), wrap);

// ---- A PHONE DOES NOT INHERIT SILENCE (V2-573) -------------------------------------------------------------
// `hb_bot_muted` is written by BOTH the speaker toggle and `togglePower()` — stopping the agent from the dock
// persists "1". So: stop the agent on the phone, start it again later from the computer, open the app, and the
// phone comes up with the agent LIVE and its own output muted, hydrated from a decision made in another session
// about a different situation. Everything looks healthy and nothing can be heard. That is the operator's
// «i couldn't listen to the voice in mobile», and it is now impossible: on this shell a page load starts with the
// voice ON, and silencing is a decision taken IN the session you are in (the toggle lives in the config sheet).
//
// Deliberately mobile-only. The desktop keeps its persisted preference — it is a machine you sit at, with the
// speaker icon permanently on screen, so there the memory is a convenience instead of a trap.
try {
  if (localStorage.getItem("hb_bot_muted") === "1") {
    store.setBotMuted(false);
    localStorage.setItem("hb_bot_muted", "0");
    api.uiEvent("mobile:voice_unmuted_on_boot", {});
  }
} catch (_) {}

const botAudio = mount(h("audio", { id: "botaudio", autoplay: true, playsinline: true }));
session.attachBotAudio(botAudio);
// Reactive icon↔audio binding: the <audio> ALWAYS reflects botMuted(), the same signal the speaker toggle paints.
// Never "icon says muted but sound comes out" (the V2-043 startup bug).
createEffect(() => { try { botAudio.muted = store.botMuted(); } catch (_) {} });

// ---- native mobile surfaces, mounted from the canonical list (shell/mobile-surfaces.js) ----
for (const s of MOBILE_SURFACES.filter((s) => s.phase === "scaffold")) mount(s.comp(), s.target === "deck" ? wrap : undefined);
for (const s of MOBILE_SURFACES.filter((s) => s.phase === "overlay")) mount(s.comp(), s.target === "deck" ? wrap : undefined);

// The inline splash in mobile/index.html did its job (a loader from the FIRST byte, which on a cold account Machine
// is tens of seconds); the BootOverlay takes over. If this module had failed to load, #preboot would stay — better
// a loader than a black screen.
// V2-558 — the ring closes on a FACT, not on a clock: `__zaelarPrebootDone` paints it full and says
// "Ready", and only then does the splash go. Guarded because preboot.js is a separate file and a shell that
// failed to load it must still be able to get rid of its own splash.
try { window.__zaelarPrebootDone?.(); } catch { /* noop */ }
try { document.getElementById("preboot")?.remove(); } catch { /* noop */ }

// ---- CLOUD profile + Energy balance: same retry loop as the desktop, for the same reason. On the COLD START of an
// account Machine these endpoints answer 503 until FastAPI finishes coming up; a single failed attempt would leave
// `cloudProfile` false FOREVER and the menu would hide the account row on a paying account. ----
(async () => {
  for (let i = 0; i < 45; i++) {
    try { const cfg = await api.getConfig(); if (cfg) { store.setCloudProfile(!!cfg.cloud_profile); return; } }
    catch { /* 503 while the Machine boots: retry */ }
    await new Promise((r) => setTimeout(r, 2000));
  }
})();
(async () => {
  for (let i = 0; i < 45; i++) {
    try {
      const r = await fetch("/api/energy", { cache: "no-store" });
      if (r.ok) { store.setEnergy(await r.json()); return; }
    } catch { /* still booting: retry */ }
    await new Promise((r) => setTimeout(r, 2000));
  }
})();

// ---- V2-101 first-run language onboarding: identical gate to the desktop's (checked ONCE after bootReady flips).
// It matters MORE here: a phone is plausibly the first place someone ever opens their agent. ----
let _langOnboardChecked = false;
createEffect(() => {
  if (_langOnboardChecked || !store.bootReady()) return;
  _langOnboardChecked = true;
  fetch("/api/i18n/state", { cache: "no-store" }).then((r) => r.json()).then((s) => {
    if (s && s.chosen === false) store.setLangOnboardOpen(true);
  }).catch(() => {});
});

// ---- THE HOST. `openSSE(deck)` is the whole point of the split: sse.js does not know which shell it is driving,
// so the brain's show/close/confirm/refresh reach the phone with zero changes to that file. ----
const deck = new Deck(stage);
window.__zaelarDesktop = deck;      // the name the SSE/session bridge looks for (session-lk.js). Kept AS IS
                                    // deliberately: renaming it would mean editing the shared session module to
                                    // teach it about a second shell, which is exactly the coupling this avoids.
window.__zaelarDeck = deck;         // …plus an honest alias, for anything mobile-only that comes later.
createEffect(() => deck.setRunning(!store.powerOff()));
openSSE(deck);
deck.restore();

// ---- the orb's two canvases are inside the dock; startVisuals only needs the elements ----
session.startVisuals({ orbCanvas: $("#orb"), vizCanvas: $("#viz") });

// ---- ALWAYS-ON voice. Identical to the desktop's: browsers require a user gesture for the mic, so we also
// (re)connect on any pointer interaction while the session is down. Idempotent, and it respects the ONE exception —
// an explicit, persisted ⏻ off, or the very tap on ⏻ would re-arm the session it just stopped. ----
function ensureVoice() {
  if (store.powerOff()) return;
  if (!store.started() && !store.starting()) session.start().catch(() => {});
}
if (store.powerOff()) store.setBootReady(true);   // nothing to wait for: don't leave the veil stuck (same as desktop)
ensureVoice();
// `pointerdown`, not `touchstart`: iOS requires a user gesture for the mic, and pointerdown fires for both.
window.addEventListener("pointerdown", ensureVoice);

// ---- AND THE OTHER HALF OF THE SAME GESTURE: UNLOCK PLAYBACK (V2-573) ---------------------------------------
// `ensureVoice()` above solves the browser's rule about the MICROPHONE. There is a second rule, about the
// SPEAKER, and this shell was only obeying the first one: a mobile browser will not start playing a remote audio
// track either until the page has had a user gesture, and `ensureVoice()` runs at LOAD, before any tap exists.
// LiveKit reports it as `room.canPlaybackAudio` and fixes it with `room.startAudio()` — which was never called
// anywhere in this codebase, on either shell. The recovery therefore depended entirely on the operator noticing
// a banner. Now the FIRST touch anywhere on the screen unlocks it, whatever that touch was for.
//
// Same listener, not a second one, and it must stay synchronous up to the SDK call: awaiting anything first
// spends the user activation and the unlock silently fails.
window.addEventListener("pointerdown", () => { try { session.unlockAudio(); } catch (_) {} });

// ---- THE VOICE LOCK, SURFACED (server/livekit_api.py: one live voice session per machine) ------------------------
// session.start() does NOT throw when the lock is held: it sets store.micBlocked and retries itself every 3 s until
// the other surface goes away (services/session-lk.js). That behaviour is RIGHT and shared — when the desktop tab
// closes, the phone picks the voice up on its own with nobody doing anything.
//
// What was missing is that on the desktop `micBlocked` paints a 🚫 ring over the orb, which is legible when "the
// other tab" is a tab you can see. Between a phone and a laptop in another room it is not: the phone would sit there
// looking like it was connecting, forever, with no hint that the voice is simply somewhere else. So the flag is
// mirrored into a mobile surface that NAMES the situation and offers the one gesture that fixes it.
createEffect(() => store.setMobileVoiceHeld(!!store.micBlocked().show && !store.powerOff()));

// ---- reconcile with the SERVER's truth about the global switch (V2-092), in the SAFE direction ----
// Identical logic to app/main.js, including the timestamp guard: this reply is a SNAPSHOT of when it was asked, not
// of when it arrives. On a machine waking from cold that is seconds, and the operator — staring at the screen
// precisely because it will not start — presses ⏻ inside that window. The slowest message must not beat the newest.
(async () => {
  try {
    const askedAt = Date.now();
    const r = await api.runState();
    if (!r || typeof r.running !== "boolean") return;
    if (store.powerCmdAt() > askedAt) return;
    if (!r.running) { store.setPowerOff(true); store.setMicMuted(true); store.setBotMuted(true); }
    else if (store.powerOff()) api.runStop();
  } catch { /* the server isn't answering yet: local state already applied */ }
})();

// STOPPED ⇒ NO VOICE SESSION, whoever gave the order (this dock, the seed above, or an SSE `run` event from the
// desktop tab). Without this the phone would paint itself off with the mic open — the state that lies, again.
createEffect(() => {
  if (!store.powerOff()) return;
  store.setBootReady(true);
  if (store.started() || store.starting()) { try { session.stop(); } catch (_) {} }
});

// ---- CLIENT STATE → observability. Same two events as the desktop, plus `shell:"mobile"` so a run can be told
// apart in the log: "it worked on the computer and not on the phone" must be answerable from the timeline. ----
let _prevAgentState = null;
createEffect(() => {
  const s = store.agentState();
  if (s === _prevAgentState) return;
  const prev = _prevAgentState;
  _prevAgentState = s;
  api.uiState("agent:state", { state: s, prev: prev || "none", shell: "mobile" });
});
try {
  document.addEventListener("visibilitychange", () => {
    // On a phone this is not an edge case, it is the normal life of the app: every incoming call, every switch to
    // another app. Without it, "it froze" and "you were in WhatsApp" are indistinguishable in the log.
    api.uiState("tab:visibility", { state: document.hidden ? "hidden" : "visible", shell: "mobile" });
  });
} catch (_) {}

// ---- SHEETS ARE MUTUALLY EXCLUSIVE. Two sheets stacked over a 6-inch screen is a dead end with no visible way
// out; the phone has no room for the desktop's "several panels open at once". Opening one closes the others. ----
createEffect(() => { if (store.chatOpen()) { store.setMobileMenuOpen(false); store.setMobileSettingsOpen(false); } });
createEffect(() => { if (store.mobileMenuOpen()) store.setChatOpen(false); });

// ---- ANDROID BACK BUTTON / iOS swipe-back. In a standalone PWA there is nowhere to go back TO, so an unhandled
// back gesture closes the app — losing the session over a reflex. Intercepted: back closes the top-most open
// surface, and only exits when there is nothing left to close. ----
function topMostClose() {
  if (store.mobileSettingsOpen()) return store.setMobileSettingsOpen(false), true;
  if (store.mobileMenuOpen()) return store.setMobileMenuOpen(false), true;
  if (store.chatOpen()) return store.setChatOpen(false), true;
  if (deck.list().length) return deck.close(deck.list()[deck.at] ?? deck.list()[0]), true;
  return false;
}
try {
  history.pushState({ zm: 1 }, "");
  window.addEventListener("popstate", () => {
    const handled = topMostClose();
    // Re-arm the trap either way: one entry always sits ahead of us, so the NEXT back press is ours too. If nothing
    // was open we still re-arm and simply do nothing — leaving the app is then the operator's second press.
    history.pushState({ zm: 1 }, "");
    if (!handled) api.uiEvent("mobile:back_noop", {});
  });
} catch (_) {}

// ---- system-status poller (keeps the agent-state signals live even with everything closed) + the voice catalog ----
startStatusPolling();
session.loadVoices();

// ---- manual control surface, mobile edition. Same shape as window.zaelar on the desktop so anything that scripts
// the UI (tests, the operator's console) works in both shells. ----
window.zaelar = {
  show: (id, q = "") => deck.show(id, { q }),
  close: (id) => (id ? deck.close(id) : deck.closeAll()),
  next: () => deck.next(),
  prev: () => deck.prev(),
  chat: (text) => submitChat(text),
  panel: () => store.setChatOpen(true),
  menu: () => store.setMobileMenuOpen(true),
  shell: "mobile",
};

// ---- /m?widget=<id> — the same deep link the desktop honours, which is also how a PWA shortcut can open straight
// into a widget (manifest.webmanifest `shortcuts`). ----
(function () {
  const w = new URLSearchParams(location.search).get("widget");
  if (w) setTimeout(() => deck.show(w), 700);
})();
