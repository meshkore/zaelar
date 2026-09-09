// attention_hold.js — a SPOKEN turn waits for the attention gate's verdict (V2-647).
//
// The mic is always open (V2-015) and the gate decides, per turn, whether the words were FOR zaelar. That
// verdict travels as its own event and arrives just AFTER the transcript, so the chat wall used to paint
// first and learn second — and never unlearned. Measured live 2026-09-09 23:18 (operator report, with the
// screenshot): an entire conversation he was having with somebody else in the room filled his chat, every
// line correctly judged «no dirigido a zaelar» server-side and answered with silence, every line shown as
// if he had said it. The canvas fast-path had the same hole and it is the worse half: room speech carrying
// «cierra» could close his widgets, which is exactly what V2-015 exists to prevent.
//
// Two rules keep the hold from becoming a new way to LOSE words:
//   · fail-open — a held turn whose verdict never arrives is released after HOLD_MS. Showing an ambient
//     line is a nuisance; swallowing a real one is the bug we are fixing.
//   · in `always` mode there is no gate to wait for, so nothing is ever held.
//
// It lives apart from `sse.js` on purpose: this is the whole decision, it has no browser dependency, and
// the tests drive THIS module — not a copy of it (the re-implemented-test lesson).
export const HOLD_MS = 2500;

export function createAttentionHold({ mode, deliver, holdMs = HOLD_MS,
                                      setTimer = setTimeout, clearTimer = clearTimeout }) {
  let held = [];
  let timer = null;

  const release = () => {
    const batch = held; held = [];
    clearTimer(timer); timer = null;
    for (const h of batch) deliver(h.text, h.isFinal);
  };

  return {
    /** A spoken turn arrived. Held until the gate rules on it (or delivered at once with no gate). */
    spoken(text, isFinal) {
      if (mode() === "always") return deliver(text, isFinal);
      held.push({ text, isFinal });
      if (!timer) timer = setTimer(release, holdMs);
    },
    /** The gate ruled. `directed` releases everything waiting; otherwise the turns this verdict COVERS are
     *  dropped — the verdict carries the accumulated phrase, so anything outside it belongs to a later turn
     *  still waiting for its own ruling. */
    verdict(verdictText, directed) {
      if (!held.length) return;
      if (directed) return release();
      const hay = (verdictText || "").toLowerCase();
      held = held.filter(h => !(!hay || hay.includes((h.text || "").toLowerCase().trim())));
      if (!held.length) { clearTimer(timer); timer = null; }
    },
    /** Testing/diagnostics only: how many turns are waiting on a verdict right now. */
    pending() { return held.length; },
  };
}
