// IS ZAELAR LISTENING TO YOU RIGHT NOW? — the ONE answer the orb's colour is painted from.
//
// The orb wears a vivid warm colour while it is listening and a pale grey while it is not (operator,
// 2026-09-09: a separate green ring «me estropea el diseño del ojo», so the orb ITSELF is the signal).
// The predicate lived inside the visualizer's draw loop, where nothing could reach it, and it was WRONG in
// the one way that matters: it never looked at the microphone. With the mic muted the orb kept glowing
// «te escucho» over an input that was closed — operator, 2026-09-10: «el orbe está de color naranja activo
// porque está escuchando todo el rato A MENOS QUE DESACTIVEMOS EL MICRO, porque entonces obviamente nada
// está escuchando».
//
// Dependency-free on purpose (the V2-647 lesson): the test drives THIS function, not a copy of its rules.
//
// Three conditions, in the order they can each kill the claim:
//   live        → `store.agentLive()`. A stopped/stalled agent hears nothing, whatever the mic says.
//   micMuted    → the operator closed the input himself. Nothing reaches the gate at all.
//   mode        → `always` listens to every utterance; `smart`/`wakeword` only inside the attention window,
//                 which is exactly what `attentionHit` means (it is set by the gate's own DIRECTED verdict
//                 and expires with the window — see store.js::pulseAttentionHit).
export function isListening(s) {
  if (!s) return false;
  if (!s.live) return false;
  if (s.micMuted) return false;
  const mode = s.mode || "always";
  if (mode === "smart" || mode === "wakeword") return !!s.attentionHit;
  return true;
}
