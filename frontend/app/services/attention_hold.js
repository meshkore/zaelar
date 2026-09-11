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
// V2-664 — BUT A FAIL-OPEN RELEASE MAY NOT MOVE WIDGETS. `deliver` receives `judged`: true only when a
// verdict actually said DIRECTED. Measured live 2026-09-11 (session eedf7f9b): while he was describing this
// widget's own failure out loud — «…que ha sido poner un vídeo…», every fragment correctly ruled AMBIENT —
// the release fired 0.36 s before the verdict landed and the canvas fast-path opened the YouTube card he had
// just closed. The two halves of the release are not equally reversible: painting an unjudged line on the
// wall is the nuisance the fail-open accepts on purpose, mutating his canvas is what V2-015 exists to stop.
// So the CHAT still fails open and the CANVAS never does.
//
// The delay is also no longer shorter than the verdict it waits for: the gate holds an unfinished sentence
// («⏸ turno RETENIDO») for as long as the operator keeps talking, so a 2.5 s deadline expired routinely on
// normal continuous speech and the hold was, in practice, not holding. A late verdict now still arrives in
// time to rule; what it costs when one never comes is that an orphan line reaches the wall later.
//
// It lives apart from `sse.js` on purpose: this is the whole decision, it has no browser dependency, and
// the tests drive THIS module — not a copy of it (the re-implemented-test lesson).
export const HOLD_MS = 9000;

export function createAttentionHold({ mode, deliver, holdMs = HOLD_MS,
                                      setTimer = setTimeout, clearTimer = clearTimeout }) {
  let held = [];
  let timer = null;

  const release = (judged) => {
    const batch = held; held = [];
    clearTimer(timer); timer = null;
    for (const h of batch) deliver(h.text, h.isFinal, judged);
  };

  return {
    /** A spoken turn arrived. Held until the gate rules on it (or delivered at once with no gate). */
    spoken(text, isFinal) {
      if (mode() === "always") return deliver(text, isFinal, true);   // no gate to wait for: it IS the verdict
      held.push({ text, isFinal });
      if (!timer) timer = setTimer(() => release(false), holdMs);     // V2-664: a timeout judged nothing
    },
    /** The gate ruled. `directed` releases everything waiting; otherwise the turns this verdict COVERS are
     *  dropped — the verdict carries the accumulated phrase, so anything outside it belongs to a later turn
     *  still waiting for its own ruling. */
    verdict(verdictText, directed) {
      if (!held.length) return;
      if (directed) return release(true);
      const hay = (verdictText || "").toLowerCase();
      held = held.filter(h => !(!hay || hay.includes((h.text || "").toLowerCase().trim())));
      if (!held.length) { clearTimer(timer); timer = null; }
    },
    /** Testing/diagnostics only: how many turns are waiting on a verdict right now. */
    pending() { return held.length; },
  };
}
