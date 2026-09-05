"""The flash turn's SECOND PASSES — one place for «compose a spoken answer from given context with the same
fast model the turn already pays» (V2-572; extracted from `probe.py` paying the architecture ratchet — the
stream-collect shape lived there in triplicate, and the repair below would have been the fourth copy).

Two passes live here today:

· `recall_answer` — the probe's recall composition (V2-135 parity), moved byte-for-byte in spirit: the memory
  block becomes a 1-3 sentence spoken answer, or "" and the caller keeps what it had.

· `bare_ack_repair` — the repair half of the bare-ack guard (`answer_guards.a_bare_ack_answers_a_question`,
  see the measured session there). ONE small second pass with the model that just failed, told exactly what
  it did and ordered to answer the question with content. It is the same recovery the operator performed by
  hand — «Respóndeme a la pregunta» — automated, so he never has to say it again.

  Why the VOICE channel gets a follow-up at all, when V2-210 deliberately keeps its sourced-answer backstop
  out of that channel (its «hablar dos veces» doctrine, written at the provider's search block): V2-210's
  improvised figure SOUNDS like a complete answer, so doubling it would replace fine-sounding speech on every
  price question. Here the first utterance carried ZERO information — «Hecho.» to «¿tenemos reservas?» — and
  the operator heard it fail twice in one session. Speaking the missing answer right after is not saying it
  twice; it is saying it once, late. The guard's narrowness (information question, no action verb, bare ack)
  is what keeps this from ever firing on a turn that was fine.
"""
from __future__ import annotations

import asyncio


async def collect(sys2: str, user_text: str, spec, max_tokens: int = 240) -> str:
    """Stream one (system, user) exchange through the fast client and return the joined text, raw."""
    from nucleo.flash.fast_client import FastClient
    parts: list[str] = []
    async for delta in FastClient().stream(
            [{"role": "system", "content": sys2}, {"role": "user", "content": user_text}],
            spec=spec, max_tokens=max_tokens):
        parts.append(delta)
    return "".join(parts)


async def recall_answer(text: str, query: str, spec, sanitize=None) -> str:
    """The recall two-pass route's spoken answer (probe channel): memory block → 1-3 natural sentences.
    Returns "" on any failure — the caller keeps its original reply. `sanitize` is the caller's own
    post-processor (the probe passes speech+dialog's), so this module never reaches into the motor for one —
    the dependency-direction ratchet (7.32) caught exactly that import here on its second day of life."""
    try:
        from nucleo.flash import dialog, prompt as _prompt
        rblock, _ = await asyncio.to_thread(_prompt.compose_recall, query)
        sys2 = (_prompt._lang_lock()
                + "\nResponde en 1-3 frases habladas y naturales usando SOLO estos datos del operador. "
                  "No menciones capas ni memoria interna; si falta algo, dilo.\n\n"
                + f"PETICIÓN: {text}\n\nDATOS:\n{rblock or '(sin datos relevantes)'}")
        raw = await collect(sys2, text, spec, max_tokens=260)
        return ((sanitize(raw) if sanitize else dialog.sanitize_reply(raw)) or "").strip()
    except Exception:
        return ""


async def bare_ack_repair(operator_text: str, window: list, spec) -> str:
    """The missing answer, composed with the recent window as context. Returns "" on any failure — the caller
    keeps what it had rather than crashing a live turn over a repair."""
    try:
        from nucleo.flash import dialog, prompt as _prompt
        ctx = "\n".join(f"{m.get('role', '?')}: {str(m.get('content', ''))[:300]}"
                        for m in (window or [])[-8:] if isinstance(m, dict))
        sys2 = (_prompt._lang_lock()
                + "\nEl operador ha hecho una PREGUNTA y la respuesta que salió fue un asentimiento vacío "
                  "(«hecho»), que no contesta nada. Responde AHORA su pregunta con contenido, en 1-2 frases "
                  "habladas y naturales, usando el CONTEXTO RECIENTE de abajo; si el dato no está en el "
                  "contexto ni lo sabes, dilo con naturalidad y ofrece mirarlo — no vuelvas a asentir sin "
                  "contenido.\n\n"
                + f"PREGUNTA DEL OPERADOR: {operator_text}"
                + ("\n\nCONTEXTO RECIENTE:\n" + ctx if ctx else ""))
        raw = await collect(sys2, operator_text, spec, max_tokens=200)
        return dialog.sanitize_reply(raw).strip()
    except Exception:
        return ""


async def empty_wait_repair(operator_text: str, window: list, spec) -> str:
    """The sibling of `bare_ack_repair` for the EMPTY WAIT (V2-587): «sigo con ello» over a question with no
    work running behind it. The instruction names the lie precisely — nothing is in progress — so the model
    answers with what it has or says honestly what it would need to do, instead of promising ghost work.
    Returns "" on any failure — the caller keeps what it had."""
    try:
        from nucleo.flash import dialog, prompt as _prompt
        ctx = "\n".join(f"{m.get('role', '?')}: {str(m.get('content', ''))[:300]}"
                        for m in (window or [])[-8:] if isinstance(m, dict))
        sys2 = (_prompt._lang_lock()
                + "\nEl operador ha hecho una PREGUNTA y la respuesta que salió fue «sigo con ello», pero NO "
                  "hay ninguna tarea en marcha: era una promesa sobre trabajo que no existe. Responde AHORA su "
                  "pregunta en 1-2 frases habladas y naturales con el CONTEXTO RECIENTE de abajo; si el dato "
                  "no está ahí ni lo sabes, dilo con naturalidad y di qué harías para averiguarlo — nunca "
                  "prometas que ya estás en ello.\n\n"
                + f"PREGUNTA DEL OPERADOR: {operator_text}"
                + ("\n\nCONTEXTO RECIENTE:\n" + ctx if ctx else ""))
        raw = await collect(sys2, operator_text, spec, max_tokens=200)
        return dialog.sanitize_reply(raw).strip()
    except Exception:
        return ""
