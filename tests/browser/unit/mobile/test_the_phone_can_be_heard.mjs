// ============================================================================
// test_the_phone_can_be_heard.mjs — THE PHONE'S VOICE COMES OUT (V2-573).
//
// Operator, 2026-09-04: «i couldnt listen to the voice in mobile». Two independent causes were measured in the
// code, either of which produces exactly that sentence, and BOTH of them are silent — the agent connects, the
// transcript scrolls, the orb animates, and nothing is heard:
//
//   1. PLAYBACK WAS NEVER UNLOCKED. Every mobile browser refuses to start playing a remote audio track until the
//      page has had a user gesture. This shell connects the session at LOAD (`ensureVoice()` runs before any tap,
//      deliberately, so the agent is live the instant the app opens), so the `play()` in TrackSubscribed rejects.
//      LiveKit reports the state as `room.canPlaybackAudio` and clears it with `room.startAudio()` — and
//      `startAudio()` was called NOWHERE in this codebase, on either shell. The only recovery was a banner the
//      operator had to notice and tap.
//   2. SILENCE WAS INHERITED. `hb_bot_muted` is persisted by the speaker toggle AND by `togglePower()`, which
//      writes "1" whenever the agent is stopped from the dock. Stop the agent on the phone, start it later from
//      the computer, reopen the app: the phone comes up with the agent live and its own output muted, hydrated
//      from a decision made in another session about another situation.
//
// These are SOURCE-level assertions on purpose: neither cause can be reproduced headlessly (there is no LiveKit
// room and no autoplay policy in a test browser), and both are wiring — a listener that must exist, a call that
// must happen inside a gesture. What CAN be measured is measured elsewhere: the dock's geometry and the orb's
// pixels in tests/browser/e2e/mobile/render_dock.py.
// ============================================================================

import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "..");
const read = (...p) => readFileSync(join(ROOT, ...p), "utf8");

let failures = 0;
function check(name, ok, detail = "") {
  if (ok) { console.log(`  ok   ${name}`); return; }
  failures++;
  console.log(`  FAIL ${name}${detail ? "\n         " + detail : ""}`);
}

// PROSE ABOUT THE PATTERN IS NOT THE PATTERN. This file's assertions are string searches over source that is
// heavily commented — deliberately so, in this codebase — and the comments EXPLAIN the very calls being asserted.
// Measured while writing this: deleting the real `room.startAudio()` call left the test green, because the
// paragraph above it says `room.startAudio()` too. Same lesson the architecture ratchet already paid for with
// its «impl PARALELA» counter. So every source read here is stripped of comments first, and the checks then
// speak about CODE.
const strip = (src) => src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^[ \t]*\/\/.*$/gm, "");
const LK = strip(read("frontend", "app", "services", "session-lk.js"));
const SESSION = strip(read("frontend", "app", "services", "session.js"));
const MAIN = strip(read("frontend", "mobile", "app", "main.js"));
const DOCK = strip(read("frontend", "mobile", "app", "shell", "DockBar.js"));
const STORE = strip(read("frontend", "app", "core", "store.js"));
const SETTINGS = strip(read("frontend", "mobile", "app", "shell", "SettingsSheet.js"));
const CSS = read("frontend", "mobile", "app", "styles.css");

// ── 1 · the unlock exists, and goes through the SDK ────────────────────────────────────────────────────────
check("session-lk exports unlockAudio()", /export\s+async\s+function\s+unlockAudio\s*\(/.test(LK));
// The element's own play() is NOT the fix on its own: with LiveKit's audio context suspended it rejects again,
// which is why the pre-V2-573 banner could be tapped and still produce nothing.
check("the unlock calls the SDK's startAudio(), not just element.play()",
  /room\.startAudio\s*\(/.test(LK),
  "unlockAudio must call room.startAudio(); a bare botAudioEl.play() is what was already there and was not enough");
check("the unlock is guarded by the SDK's own verdict",
  /room\.canPlaybackAudio\s*===\s*false/.test(LK),
  "gate startAudio() on canPlaybackAudio, so an unlocked room is a cheap no-op on every pointerdown");

// ── 2 · the shell learns about a block instead of waiting to be told ───────────────────────────────────────
check("the room's playback status is subscribed",
  /RoomEvent\.AudioPlaybackStatusChanged/.test(LK),
  "without this listener the shell only learns about a block from a track that happens to arrive, and never "
  + "learns that playback was RESTORED");
check("the blocked state is a store signal, not only a banner",
  /export const \[audioBlocked, setAudioBlocked\]/.test(STORE));
check("the orb wears the blocked state", /audioBlocked\(\)/.test(DOCK) && /zm-blocked/.test(DOCK),
  "an operator who cannot hear the agent looks at the ORB; the ring must ride it");
check("the blocked ring is actually drawn", /\.zm-orb-btn\.zm-blocked\s*\{/.test(CSS));

// ── 3 · the first touch anywhere unlocks it ────────────────────────────────────────────────────────────────
// `ensureVoice()` had solved the browser's rule about the MICROPHONE with exactly this listener since V2-124;
// the rule about the SPEAKER went unhandled next to it for six weeks.
check("the mobile shell unlocks audio on a pointerdown",
  /addEventListener\("pointerdown"[\s\S]{0,160}unlockAudio\s*\(/.test(MAIN),
  "the first touch is the only user gesture the shell is guaranteed to get; it must carry the unlock");
check("starting the agent from the dock also unlocks",
  /unlockAudio/.test(DOCK),
  "tapping ⏻ to start IS a user gesture — the best one available — and it must not be wasted");
// The non-LiveKit engine is served at the same URL by server/livekit_api.py, so a namespace missing this export
// would throw inside a pointerdown handler on any deployment that ever falls back to it.
check("the other session engine exports it too (namespace parity)",
  /export\s+async\s+function\s+unlockAudio\s*\(/.test(SESSION));

// ── 3b · silence stays REACHABLE ───────────────────────────────────────────────────────────────────────────
// The dock restyle removed the speaker button, and the settings sheet used to say — correctly, then — that a
// speaker row would be redundant clutter. Shipping both facts together would have deleted the ONLY way to
// silence the agent from the phone. A control that exists nowhere is worse than one that takes two taps.
check("the speaker toggle exists somewhere in the shell",
  /toggleBotMute/.test(SETTINGS) || /toggleBotMute/.test(DOCK),
  "neither the dock nor the settings sheet can mute zaelar's voice; the phone has lost the control entirely");

// ── 4 · a phone does not inherit silence ───────────────────────────────────────────────────────────────────
check("a persisted mute is cleared when the phone boots",
  /hb_bot_muted"\)\s*===\s*"1"[\s\S]{0,220}setBotMuted\(false\)/.test(MAIN),
  "mobile/app/main.js must not hydrate botMuted from a previous session: the speaker control is inside the "
  + "config sheet now, so an inherited mute is invisible and unreachable");
check("…and the cleared state is written back, not left disagreeing with storage",
  /hb_bot_muted"\)\s*===\s*"1"[\s\S]{0,260}setItem\("hb_bot_muted",\s*"0"\)/.test(MAIN),
  "clearing the signal without clearing the key leaves the next reload muted again");
// The DESKTOP is deliberately untouched: it is a machine you sit at, with the speaker icon permanently on
// screen, so there the memory is a convenience. A guard, because "fix it everywhere" is the tempting edit.
check("the desktop keeps its persisted preference",
  !/hb_bot_muted"\)\s*===\s*"1"[\s\S]{0,200}setBotMuted\(false\)/.test(strip(read("frontend", "app", "main.js"))),
  "app/main.js now clears the persisted mute too; that decision was made for the phone, not for the desk");

console.log(failures ? `\n${failures} FAILURE(S)` : "\nALL OK");
process.exit(failures ? 1 : 0);
