// V2-745 — the chat beside a live voice is a TRANSCRIPT of that voice, not a draft of it.
//
// The operator, session 8fc3e1c9 (2026-09-21), a brand-new agent from power-on to stop:
//
//   «Este texto que has puesto ahí, de "me alegra que lo veas mejor", NO HA LLEGADO NI A SONAR… la gente
//    que esté mirando el chat y esté escuchando a la vez dirá: y esta frase no la ha llegado a pronunciar.
//    Si hay una locución y estás hablándome y a mitad del texto corto, EL TEXTO QUE NO HAS DICHO NO QUIERO
//    QUE EXISTA… para que el chat realmente refleje la conversación de voz que estamos teniendo.»
//
//   «Mientras vas escribiendo, va componiendo la frase, y en el momento en que la vas a consolidar, LA
//    CONVIERTES EN DOS FRASES SEPARADAS. Cuando es el mismo párrafo…»
//
//   «Cuando paso de tres, cuatro o cinco palabras, LAS ANTIGUAS DESAPARECEN y empiezas a escribir las
//    nuevas… parece que se está perdiendo texto.»
//
// Three complaints, two mechanisms, and the second is the same fact seen twice: the STT segments a
// paragraph and the wall treated a segment as a turn. Measured in his session — one sentence of his
// arrived as ELEVEN transcript events, each painted as its own bubble, with the caption resetting to the
// newest fragment each time one closed.
//
// This file drives the REAL store and the REAL hold; the numbers in every comment are from that session.
import assert from "node:assert/strict";

// A DOM stub good enough for `store.js`, which reaches for localStorage and window on import.
const mem = new Map();
globalThis.localStorage = {
  getItem: k => (mem.has(k) ? mem.get(k) : null),
  setItem: (k, v) => mem.set(k, String(v)),
  removeItem: k => mem.delete(k),
};
globalThis.window = { addEventListener() {}, location: { href: "http://127.0.0.1/" } };
globalThis.document = { addEventListener() {}, documentElement: { style: { setProperty() {} } } };

const store = await import("../../../../frontend/app/core/store.js");
const { createAttentionHold } = await import("../../../../frontend/app/services/attention_hold.js");

const agentLines = () => store.chatMsgs().filter(m => m.role === "agent").map(m => m.text);
const reset = () => store.setChatMsgs(() => []);

// ══ 1 · ONE PARAGRAPH IS ONE BUBBLE ═════════════════════════════════════════════════════════════════
// His own sentence, as Deepgram actually delivered it (session 8fc3e1c9, +84.2 s to +92.0 s).
{
  const wall = [], canvas = [];
  const hold = createAttentionHold({
    mode: () => "smart",
    deliver: (text, isFinal, judged, whole) => (whole ? wall : canvas).push(text),
  });
  const fragments = ["Vale, te he oído la voz al", "cabo de",
                     "cinco o diez segundos, o sea, perdón, al cabo de diez o quince segundos,",
                     "lo cual no entiendo."];
  for (const f of fragments) hold.spoken(f, true);
  hold.verdict(fragments.join(" "), true);

  assert.deepEqual(wall, [fragments.join(" ")],
    "THE BUG: one dictated paragraph became one bubble per STT segment — «la conviertes en dos frases " +
    `separadas cuando es el mismo párrafo». Got ${JSON.stringify(wall)}`);
  assert.equal(canvas.length, 4,
    "…and the CANVAS still sees every fragment: V2-664 tuned that path against fragments, and widening " +
    "its input is a different change nobody has measured");
}

// ══ 2 · THE CAPTION KEEPS WHAT HE ALREADY SAID ══════════════════════════════════════════════════════
{
  const hold = createAttentionHold({ mode: () => "smart", deliver: () => {} });
  assert.equal(hold.spokenSoFar(), "", "between turns there is nothing to carry");
  hold.spoken("Vale, te he oído la voz al", true);
  hold.spoken("cabo de", true);
  assert.equal(hold.spokenSoFar(), "Vale, te he oído la voz al cabo de",
    "THE BUG: the words of the turn already finished vanished when Deepgram opened the next segment, and " +
    "the caption showed the newest fragment alone — «las antiguas desaparecen»");
  hold.verdict("Vale, te he oído la voz al cabo de", true);
  assert.equal(hold.spokenSoFar(), "", "and it is empty again once the turn has landed");
}

// ══ 3 · A LINE THE VOICE NEVER SAID DOES NOT SURVIVE ════════════════════════════════════════════════
// +157.14 s: the reply «Me alegra que lo veas mejor…» is generated · +157.42 s: ElevenLabs synthesises
// 14.05 s of audio · `bot_speech` never leaves `idle`. He had started his next sentence two seconds
// earlier, so the utterance was cancelled before its first frame — and the wall kept the whole thing.
{
  reset();
  store.pushAgentChat("Me alegra que lo veas mejor, y tienes razón en lo de las dos frases.",
                      { voiced: true });
  assert.equal(agentLines().length, 1, "it is painted at once — that speed is what V2-116 bought");

  store.pushCaptionSeg("seg-filler", "Sí…", true);                  // +161.9 s: the NEXT turn's filler sounds
  store.pushAgentChat("Te tomo nota de las dos cosas.", { voiced: true });   // …and its reply settles this
  assert.deepEqual(agentLines(), ["Te tomo nota de las dos cosas."],
    "THE BUG: «no ha llegado ni a sonar» and it stayed on the wall anyway. A line the voice never opened " +
    "its mouth for must not exist");
}

// ══ 3b · …BUT SILENCE ON THE CHANNEL IS NOT PROOF THAT NOTHING WAS SAID ═════════════════════════════
// The distinction that keeps group 3 from becoming a way to lose replies: if not one caption segment has
// arrived since the line was painted, «it was never said» and «nobody told us» are indistinguishable, and
// they have opposite right answers. Removal needs evidence that the voice was busy elsewhere.
{
  reset();
  store.pushAgentChat("Una respuesta sobre la que no llega ni una sola pista.", { voiced: true });
  store.pushAgentChat("La siguiente.", { voiced: true });
  assert.deepEqual(agentLines(), ["Una respuesta sobre la que no llega ni una sola pista.", "La siguiente."],
    "with no caption movement at all since it was painted, the line stays: absence of evidence is not " +
    "evidence of absence");
}

// ══ 4 · A LINE CUT IN HALF IS KEPT AT THE POINT THE VOICE STOPPED ═══════════════════════════════════
// +163.06 s the reply; +169.08 s the spoken record came back as «Te tomo nota de las dos cosas: el texto
// que parece borrarse» — and was DISCARDED, because the rule said the longer version wins.
{
  reset();
  const full = "Te tomo nota de las dos cosas: el texto que parece borrarse un instante mientras dictas, " +
               "y esos diez segundos de silencio al arrancar.";
  const heard = "Te tomo nota de las dos cosas: el texto que parece borrarse";
  store.pushAgentChat(full, { voiced: true });
  store.pushCaptionSeg("seg-b", "Te tomo nota de las dos", false);
  store.pushCaptionSeg("seg-b", heard, true);                        // final: the barge-in stopped it here
  assert.deepEqual(agentLines(), [heard + "…"],
    `THE BUG: the wall kept what the agent MEANT to say. Got ${JSON.stringify(agentLines())}`);
}

// ══ 5 · …AND THE SPOKEN RECORD ALSO WINS WHEN IT ARRIVES AS A TRANSCRIPT ════════════════════════════
// The fallback path, for a build whose audio-synced captions never fire: LiveKit closes the conversation
// item with what it actually voiced, and that is what the wall must end up showing.
{
  reset();
  store.pushAgentChat("...tienes razón, a veces tardo un poco en arrancar. ¿Cómo te llamas?", { voiced: true });
  store.pushAgentChat("...tienes", { spoken: true });
  assert.deepEqual(agentLines(), ["...tienes…"],
    "a transcript that is a strict PREFIX of what is rendered means the speech was cut there");
}

// ══ 6 · WHAT WAS FULLY SAID IS LEFT EXACTLY ALONE ═══════════════════════════════════════════════════
{
  reset();
  const said = "Hola, soy Zaelar. ¿Cómo te llamas?";
  store.pushAgentChat(said, { voiced: true });
  store.pushCaptionSeg("seg-c", said, true);
  store.pushAgentChat(said, { spoken: true });
  assert.deepEqual(agentLines(), [said], "a complete reply keeps its text, with no ellipsis and no trim");
}

// ══ 7 · A WHOLE SESSION WITH NO CAPTION CHANNEL IS UNTOUCHED ═══════════════════════════════════════
// The failure mode that would be worse than the one being fixed: a build where the synchronizer is off,
// or a transport that never forwards it, must keep every line exactly as it does today. Group 3b proves
// the per-line half of this; here it is the whole session, in a module that never sees one segment.
{
  const fresh = await import("../../../../frontend/app/core/store.js?no-captions=1");
  fresh.setChatMsgs(() => []);
  for (const line of ["Una respuesta entera.", "Otra.", "Y otra más."]) {
    fresh.pushAgentChat(line, { voiced: true });
  }
  const lines = fresh.chatMsgs().filter(m => m.role === "agent").map(m => m.text);
  assert.deepEqual(lines, ["Una respuesta entera.", "Otra.", "Y otra más."],
    "with no caption channel ever heard from, NOTHING is trimmed — silence is not proof that nothing " +
    "was said, and erasing the wall on it would be the worse bug");
}

// ══ 8 · A TYPED/PROACTIVE LINE IS NOT OWED TO THE VOICE ═════════════════════════════════════════════
{
  reset();
  store.pushCaptionSeg("seg-d", "algo", true);
  store.pushAgentChat("🔔 Te recuerdo la cita de mañana.");          // no `voiced`: nobody promised to say it
  store.pushAgentChat("Otra cosa.", { voiced: true });
  assert.ok(agentLines().includes("🔔 Te recuerdo la cita de mañana."),
    "a notification or a text-channel reply is not a promise of speech and must never be swept");
}

console.log("ok — the wall is a transcript of the voice (9 groups)");
