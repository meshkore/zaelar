// V2-648 — the orb's warm colour is a CLAIM: «te estoy escuchando». It must never be made over a closed mic.
//
// Operator, 2026-09-10: «cuando el modo de word activation está quitado, el orbe está de color naranja activo
// porque está escuchando todo el rato — A MENOS QUE DESACTIVEMOS EL MICRO, porque entonces obviamente nada
// está escuchando». The predicate used to read powerOff + attention mode and nothing else, so muting the
// microphone left the orb glowing over an input that was shut.
//
// Drives the REAL module (`services/listening.js`), never a copy of its rules.
import assert from "node:assert/strict";
import { isListening } from "../../../../frontend/app/services/listening.js";

const live = (o = {}) => ({ live: true, micMuted: false, mode: "always", attentionHit: false, ...o });

// ── the operator's own sentence: wake-word OFF means listening all the time ──
assert.equal(isListening(live()), true, "always mode with a live agent and an open mic IS listening");

// ── …unless the mic is closed. The case that was wrong, in EVERY mode ──
assert.equal(isListening(live({ micMuted: true })), false, "a muted mic listens to nothing (always mode)");
assert.equal(isListening(live({ mode: "smart", micMuted: true, attentionHit: true })), false,
             "a muted mic listens to nothing even inside the attention window");

// ── a stopped or fallen agent hears nothing, whatever the mic says ──
assert.equal(isListening(live({ live: false })), false, "a stopped agent is not listening");
assert.equal(isListening(live({ live: false, mode: "smart", attentionHit: true })), false,
             "not even with a directed verdict still on screen from before it fell");

// ── Modo Nombre: only inside the window the gate opened ──
assert.equal(isListening(live({ mode: "smart" })), false, "wake-word mode outside the window is NOT listening");
assert.equal(isListening(live({ mode: "smart", attentionHit: true })), true,
             "wake-word mode inside the attention window IS listening");
assert.equal(isListening(live({ mode: "wakeword", attentionHit: true })), true,
             "the raw `wakeword` mode behaves like `smart` here");

// ── an unreadable state never claims to be listening: a false grey is a nuisance, a false orange is the bug ──
assert.equal(isListening(null), false, "no state at all must not claim to be listening");
assert.equal(isListening({}), false, "an empty state must not claim to be listening");

console.log("ok");
