"""A tool ROUND: the words that speak the result of a tool the model called this turn (V2-851 F5).

The model asked for data with a tool — `recall` here, `read_widget`, `web_search` and the op answer through the
channel's `speak` seam — and this round composes the answer from what came back. It is the second half of the model's
OWN call, not a re-run of the turn: nothing here fires on a sentence the model did not ask about. What died in F5 was
the other kind, `second_pass`: the repairs that ran the model again over a reply it had already given (a bare ack, an
empty wait, a mute cover, a promise to look, an answer from state, the hollow-turn seam). Their door test counts the
model calls after the main stream that no tool of the turn asked for: zero.

`still_held` is the round's guard against repeating what the turn already said: deterministic — the model is asked,
the engine checks.
"""
from __future__ import annotations

from loguru import logger


def still_held(head: str, said: str) -> bool:
    """Keep holding a second pass that has said nothing new yet: it could still be the SKIP word, or it is so far
    a repetition, from its first word, of what this turn already said. Demo pass 144, E1: the op-answer pass was asked to answer SKIP
    when the words already said answered, and spoke them again verbatim — «Yep — they did… Yep — they did…».
    A pass that ends while still held is never spoken. Deterministic: the model is asked, the engine checks."""
    import re
    if len(head) < 4 and "SKIP".startswith(head.upper()):
        return True
    hw, sw = (re.sub(r"[^\w]+", " ", str(t or "").lower()).split() for t in (head, said))
    if not hw or len(hw) > len(sw) or hw[:-1] != sw[:len(hw) - 1]:
        return False
    last_done = not str(head)[-1:].isalnum()      # a word followed by a space or a stop is whole, not a prefix
    return hw[-1] == sw[len(hw) - 1] if last_done else sw[len(hw) - 1].startswith(hw[-1])



async def collect(sys2: str, user_text: str, spec, max_tokens: int = 240) -> str:
    """Stream one (system, user) exchange through the fast client and return the joined text, raw."""
    from nucleo.llm.fast_client import FastClient
    parts: list[str] = []
    async for delta in FastClient().stream(
            [{"role": "system", "content": sys2}, {"role": "user", "content": user_text}],
            spec=spec, max_tokens=max_tokens):
        parts.append(delta)
    return "".join(parts)


async def recall_spoken(text: str, query: str, spec, emit, speak) -> str | None:
    """The VOICE channel's whole `recall` second pass — the durable memory composed straight into the mouth.

    It lived hand-rolled in the provider while `recall_answer` right below it did the same job for the probe:
    the same block, the same prose, written twice (V2-252's failure mode, with the module for it already here).
    Extracted 2026-09-11 paying the architecture ratchet, which the `read_widget` route had turned red — and the
    duplication is what the ratchet was pointing at.

    `speak` is the channel's own (system, user, max_tokens) → mouth seam: this module must not import
    `voice.engine.*` (V2-569), and the streaming/tag accumulation belongs to the provider's turn state.
    `compose_recall` goes off the event loop — it does embeddings over HTTP (the V2-004 regression)."""
    import asyncio as _asyncio
    import time as _time

    from nucleo.turn.prompt import builder as _prompt_mod
    from nucleo.flash import recall_heuristics as _rh
    emit("brain", "🧠 recall por tool", text=query, role="system")
    _t = _time.time()
    try:
        block, _ids = await _asyncio.to_thread(_prompt_mod.compose_recall, query)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"recall tool falló (voz sigue): {e}")
        block = ""
    if not (block or "").strip() and _rh.names_thread_position(text):
        # fix02 (session 6d19df41): the turn points at the LIVE thread («four messages behind»), and the
        # pills came back empty — composing from that void is what narrated the emptiness as no-access
        # («I can't reveal any hidden message... secret information»). Nothing is spoken here; the caller
        # asks which message through the deterministic clarify instead. Returns "empty_thread", None otherwise.
        emit("memory", "recall (tool del modelo) — vacío ante posición de hilo", role="system", text=query,
             extra={"layer": "long", "chars": 0, "mem_ms": round((_time.time() - _t) * 1000)})
        return "empty_thread"
    emit("memory", "recall (tool del modelo)", role="system", text=query,
         extra={"layer": "long", "chars": len(block or ""), "mem_ms": round((_time.time() - _t) * 1000)})
    await speak(
        _prompt_mod._lang_lock()
        + "\nNecesitabas RECORDAR cosas del operador para este turno; aquí están tus recuerdos "
        "relevantes. Responde a su petición en 1-3 frases HABLADAS y naturales usando SOLO lo que dan de "
        "sí los recuerdos y la conversación; si falta algo, dilo con naturalidad y pregunta lo que "
        "necesites. JAMÁS menciones «memoria», «recuerdos guardados» ni capas internas — hablas como "
        "quien simplemente se acuerda.\n\n"
        f"PETICIÓN DEL OPERADOR: {text}\n\nLO QUE SABES DE ÉL:\n{block or '(nada relevante guardado)'}",
        text, 260, "recall compose")


