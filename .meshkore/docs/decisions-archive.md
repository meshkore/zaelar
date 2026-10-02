

## Moved on 2026-10-02 (V2-778 F2-19)

- **A PHASE of the relationship has its own prompt, and it archives itself — context packs (V2-675,
  2026-09-11)**: the operator's second half of the same message — «una excepción al inicio en el que la
  conversación fuera guiada por el agente… ¿quién eres? ¿cómo te llamas? ¿dónde vives? ¿qué podría hacer por
  ti?», «tiene que conocerse a sí mismo y saber quién es y sus capacidades», and the architectural ask that
  outlives the feature: «este sistema de prompts que podamos inyectar en ciertas fases o en ciertos momentos
  o en ciertas situaciones es un sistema bastante potente que podría formar parte de nuestra arquitectura…
  de momento solo tendrá esta parte inicial», with the closing rule — «cuando ya hemos terminado con eso,
  esos prompts iniciales desaparecen y ya pasamos a la fase normal». **Three things already put text in the
  turn and none of them is this**: the resource layer is what the agent ALWAYS is (and is cached as the
  stable prefix, V2-536, which is precisely why a phase block may never live there — a cached block keeps
  being spoken after its phase is over); `_directive_block` is ONE style preference he gave this session;
  `live_state()` is what is true this second. A pack is the fourth thing, and the registry
  (`nucleo/context_packs/`) enforces what keeps it from becoming a permanent tax: it is re-judged EVERY turn
  from a cheap local read, an archived pack answers False for good, and **the catch is PER PACK** — one net
  around the whole section would let a single broken pack silently delete every other phase's contribution,
  producing a turn that looks exactly like the steady state. **The INTRODUCTION is the only pack today**, and
  it was measured first: the kickoff asked his name, he answered around it, and `operator_name` was still
  `None` three sessions later — there WAS no phase, so whether the two ever met depended on whether one
  greeting happened to land. The block says what to DO this turn and never what the agent IS, asks ONE thing
  at a time and drops it if he deflects, and **deliberately does not list the widgets**: the resource layer
  already carries the live catalog in the same prompt, and a second inventory written by hand is how two
  lists end up disagreeing (V2-594, V2-603). His «tampoco hace falta que se pase cuatro minutos hablando» is
  in there as a hard rule: two or three capabilities chosen from what he has already said about himself, then
  stop. **Closing it is the hard half**, and he asked for it to be ours and, where needed, a model's: three
  exits, cheapest first — DETERMINISTIC (we know his name, the one fact the phase exists to learn, and the
  memory writes it on its own, so the common case ends with no extra call at all), a JUDGE off the hot path
  and rationed (nothing is settled before four turns, then one call every four), and a CAP (an introduction
  still running after thirty turns is not introducing). **An unreachable judge leaves the phase OPEN** — a
  network blip must not silently skip the introduction — while unreadable settings mean NO phase, because a
  missing block costs a plainer first conversation and a block that cannot be turned off costs every turn
  forever. Watched from the bus (`turn.completed`), the Susurro/actionmap pattern: zero coupling with the
  voice provider, and it covers BOTH channels for free. The flag lives in `AGENT_KEYS`, so a factory reset
  correctly starts the relationship over. **And the phrasebook of V2-674 stands aside while a phase is
  guiding**: during the introduction «hola» is not small talk, it is the first move of a conversation that
  has somewhere to go — his own «excepción al inicio», and the reason the two batches are one. Node **3.38**;
  seventeen disarms, mutations asserted, all red — one came back GREEN and the TEST was wrong: it measured
  `compose()`'s outer net instead of the per-pack catch it claimed to be about, and now asserts that a
  healthy pack SURVIVES a broken neighbour. Ratchet paid by EXTRACTING the cron line to `live_blocks.py`
  (the browser/background-block precedent), and prompt.py's ceiling comes DOWN 854 → 834.
