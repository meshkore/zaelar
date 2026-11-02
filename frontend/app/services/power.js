// power.js — THE ONE DOOR to switch the agent on or off, and the one rule for a tap on the centre (V2-792 §9).
//
// The desktop's ⏻ (Orb.js) had the right ORDER since 2026-08-31 — the server first, the voice session after, with
// the hand-off stamp keeping every other road shut meanwhile (V2-627) — and the phone's dock had its own copy that
// started the session FIRST: the server, still stopped, refused it (`voice:refused server_stopped`) and the phone
// sat «off» over a running agent (operator's Machine, 2026-10-25 22:40:17). One body now, for every face.
//
// And the centre — the desktop bar slot, the phone orb — is ONE tap rule read from `store.screenState()`. The trap
// it removes: on a screen whose voice lived elsewhere the centre wore the ⏻ face of «stopped», and pressing it to
// «switch it on» stopped the whole agent, the phone the operator was talking to included.
import * as store from "../core/store.js?v=2";
import * as api from "./api.js?v=2";
import * as mic from "./mic.js?v=1";
import * as session from "./session.js?v=3";

/** Switch the agent off (`off` true) or on. `where` names the control, for the audit. */
export function setPower(off, where = "orb") {
  // V2-627, the operator's own request: say it on every press, with the state it was in.
  console.info("[zaelar] ⏻ " + (off ? "OFF" : "ON") + " — agent was " + store.agentState());
  // Stamp BEFORE applying: a reconciliation that fetched the state before this instant is history (store.js).
  store.markPowerCommand();
  store.clearPowerOnPending();          // a newer press supersedes an older one, hand-off included (V2-627)
  store.setPowerOff(off);
  if (off) {
    // ⏻ blocks EVERYTHING (V2-066): the session (mic tracks, speaker), the work session, and the server's GLOBAL
    // switch, which freezes workers, suspends producing widgets, cuts crons and blocks new work (V2-092).
    try { session.stop(); } catch (_) {}
    api.obsSessionEnd("power_off", "button");
    mic.setMuted(true, "power-off");    // V2-654: through the door — icon, storage, track and engine together
    store.setBotMuted(true); try { localStorage.setItem("hb_bot_muted", "1"); } catch (_) {}
    try { store.fetchTasks(); } catch (_) {}
    api.runStop("button").then(() => store.fetchTasks());
  } else {
    mic.setMuted(false, "power-on");
    store.setBotMuted(false); try { localStorage.setItem("hb_bot_muted", "0"); } catch (_) {}
    // ORDER: the SERVER first, the voice session AFTER (2026-08-31). `session.start()` gates on the server's truth,
    // so starting before `runStart()` landed made it read the state from before this very click and abort. The
    // hand-off stamp keeps every other road (main.js's «power came back» effect, the phone's ensureVoice) shut
    // until the server answered; it expires on its own, so a reply that never comes cannot wedge the voice.
    store.markPowerOnPending();
    api.runStart("button").then(() => {
      store.clearPowerOnPending();
      store.fetchTasks();
      try { session.start(); } catch (_) {}
    });
  }
  // The phone's first touch is also the gesture a mobile browser needs to play audio (V2-573).
  try { session.unlockAudio && session.unlockAudio(); } catch (_) {}
  api.uiEvent(where === "dock" ? "mobile:power" : "orb:power", { state: off ? "off" : "on" });
}

export function togglePower(where = "orb") { setPower(!store.powerOff(), where); }

/** A tap on the centre of the bar or the dock — what it does depends on what this screen IS. */
export function centreTap(where = "bar") {
  const s = store.screenState();
  api.uiEvent("centre:tap", { state: s, where });
  if (s === "off") return setPower(false, where);
  if (s === "secondary") {
    // Bring the voice HERE: the mic and the speaker open on this screen, and every other screen turns both off.
    return Promise.resolve(session.openMicHere && session.openMicHere(where))
      .then(() => { if (store.botMuted()) session.toggleBotMute(); });
  }
  if (s === "stalled") { try { session.start(); } catch (_) {} return; }
  if (s === "holder" || s === "speaking") return setPower(true, where);
  // starting / pausing: in transit — a tap must not fire a second command into it
}
