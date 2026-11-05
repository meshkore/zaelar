// ============================================================================
// event-scope.js — WHICH SCREEN an event is for (V2-792: one agent, one voice, many screens).
//
// One engine serves the desktop tab and the phone at once, and every event of the stream reaches both. That is
// right for what the conversation IS (the transcript, the chat, an errand's progress, a notice, the battery) and
// wrong for what a request DOES TO A SCREEN: a video asked for on the desktop opened, and played, on the phone too.
//
// The server stamps each event with `origin_dev`, the screen the turn came from (`voice/screens.py`). This map
// says which events that stamp governs. It is DATA on purpose: scoping by `if`s scattered through sse.js is how
// the widget flags decayed, and a structural test reads this table (node 4.240).
//
//   all     → applied on every screen (the default: anything not listed below)
//   origin  → applied on the screen that asked; every other screen shows a passive chip at most
// ============================================================================

export const ORIGIN_SCOPED = {
  // What a request does to a screen's LAYOUT. `close`, `data`, `confirm`, `modify` stay global: closing a card
  // that is not open is a no-op, and a video playing on the desktop must obey «páralo» said to the phone.
  widget: ["show", "create", "fullscreen", "move", "resize", "arrange", "minimize"],
  // The native panel (chat, processes, connectors): «abre el chat» on the phone does not open the desktop's.
  panel: "*",
};

// Every other kind the stream carries, declared on purpose: the conversation and the agent's state are the same on
// every screen. A kind routed in sse.js that is in NEITHER table fails node 4.240 — a new kind decides its scope.
export const ALL_SCREENS = [
  "alert", "ambient", "ask", "bot_speech", "brain", "cluster", "energy", "error", "filler", "interim", "language",
  "memory", "notify", "pulse", "run", "screens", "secret", "session", "state", "status", "task", "task_state",
  "transcript", "ui", "vad",
];

/** The scope of one event: "origin" or "all". */
export function scopeOf(d) {
  const rule = d && ORIGIN_SCOPED[d.kind];
  if (!rule) return "all";
  if (rule === "*") return "origin";
  return rule.includes(String(d.label || "")) ? "origin" : "all";
}

/** What THIS screen does with the event: "apply", or "elsewhere" (it belongs to another screen).
 *  An event with no stamp is applied everywhere — an older engine, or a cause with no screen behind it. */
export function placement(d, device) {
  if (scopeOf(d) !== "origin") return "apply";
  const o = String((d && d.origin_dev) || "");
  if (!o || !device || o === device) return "apply";
  return "elsewhere";
}

/** «phone» / «computer» — which word names the screen a device id belongs to. */
export function surfaceOf(dev) {
  const d = String(dev || "");
  return d.startsWith("mobile:") ? "phone" : d.startsWith("desktop:") ? "computer" : "";
}
