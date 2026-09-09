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


async def mute_cover_repair(operator_text: str, window: list, spec) -> str:
    """The third sibling (V2-642): the reply came out EMPTY after a wait lead-in already sounded. The
    instruction names the hole — nothing was said at all — so the model either answers now or closes
    honestly; it may never leave the lead-in hanging. Returns "" on any failure — the caller then speaks
    the deterministic closer instead, because this turn ending mute is the one outcome that cannot happen."""
    try:
        from nucleo.flash import dialog, prompt as _prompt
        ctx = "\n".join(f"{m.get('role', '?')}: {str(m.get('content', ''))[:300]}"
                        for m in (window or [])[-8:] if isinstance(m, dict))
        sys2 = (_prompt._lang_lock()
                + "\nEl operador ha dicho algo y tu turno salió VACÍO: sonó una muletilla de espera y después "
                  "nada — se quedó colgado esperando. Contesta AHORA en 1-2 frases habladas y naturales usando "
                  "el CONTEXTO RECIENTE de abajo; si de verdad no tienes respuesta, CIERRA con honestidad "
                  "(«pues ahora mismo no tengo una buena respuesta a eso») — lo único prohibido es no decir "
                  "nada.\n\n"
                + f"LO QUE DIJO EL OPERADOR: {operator_text}"
                + ("\n\nCONTEXTO RECIENTE:\n" + ctx if ctx else ""))
        raw = await collect(sys2, operator_text, spec, max_tokens=200)
        return dialog.sanitize_reply(raw).strip()
    except Exception:
        return ""


def continuity_truth() -> str:
    """The honest sentence for «are you still on it?» when nothing runs (V2-645) — DETERMINISTIC, never
    composed: the state is ours to say, and a second model pass over the same window that produced the lie
    could reproduce it. Names the way out the confirm gate is actually holding open, when it is."""
    try:
        from nucleo import dispatch as _dd
        if (_dd.confirm_line() or "").strip():
            return ("La verdad: ahora mismo no hay ninguna tarea en marcha — se quedó parada esperando tu "
                    "confirmación. Dime «sí» y la lanzo ya.")
    except Exception:  # noqa: BLE001
        pass
    return "La verdad: ahora mismo no hay ninguna tarea en marcha — se perdió. ¿La vuelvo a lanzar?"


async def probe_hollow_repairs(operator_text: str, spoken: str, window: list, spec) -> str:
    """The PROBE channel's post-turn repairs (V2-572/587/645) — extracted here from probe.py so the two
    channels share one home instead of a documented parallel impl (and probe.py pays its size ratchet by
    extraction, per the house rule). The probe has no audio covers, so the mute-cover shape cannot happen
    here; it re-composes instead of speaking follow-ups — except the continuity truth, deterministic in
    both channels. Any internal failure returns what it was given."""
    try:
        from nucleo.flash import answer_guards as _ag
        from nucleo.flash import dialog as _dialog
        try:
            from nucleo import dispatch as _d
            running = bool(_d.has_active())
        except Exception:  # noqa: BLE001
            running = True                       # fail-safe: unreadable liveness counts as running (V2-587)
        if _ag.a_bare_ack_answers_a_question(operator_text, spoken):
            return (await bare_ack_repair(operator_text, _dialog.prune_window(window), spec)) or spoken
        if _ag.a_continuity_claim_over_nothing(operator_text, spoken, acted=False, anything_running=running):
            return (spoken + " " + continuity_truth()).strip()    # V2-645 mirror
        if _ag.an_empty_wait_answers_a_question(operator_text, spoken, acted=False, anything_running=running):
            return (await empty_wait_repair(operator_text, _dialog.prune_window(window), spec)) or spoken
    except Exception:  # noqa: BLE001
        pass
    return spoken


async def hollow_repairs(text: str, spoken_text: str, window: list, spec, *,
                         did_act: bool, covered: bool, speak, emit, pick_closer=None) -> str:
    """ONE seam for the three hollow-turn repairs — the shapes a completed turn may not end in:
      · V2-572: an information question answered with a bare «Hecho.» → compose the missing answer;
      · V2-587: the same question answered with «sigo con ello» while NOTHING runs → compose it;
      · V2-642: a MUTE completion after a sounded cover (or over a question) → compose, else speak the
        deterministic honest closer (`pick_closer`) — after «Déjame que mire…», silence is never an option.
    Extracted here from the provider (the file-size ratchet: nucleo.py sat exactly at its ceiling) and
    called by the voice channel; the probe channel keeps its own parallel wiring of the first two, and the
    third cannot happen there (the probe has no audio covers). Returns the final spoken text; any internal
    failure returns what it was given — a repair must never take down a live turn."""
    try:
        from nucleo.flash import answer_guards as _ag
        try:
            from nucleo import dispatch as _d
            running = bool(_d.has_active())
        except Exception:
            running = True                       # fail-safe: unreadable liveness counts as running (V2-587)
        if _ag.a_bare_ack_answers_a_question(text, spoken_text):
            emit("brain", "🚧 pregunta contestada con un «hecho» vacío — compongo la respuesta que falta",
                 text=text[:160], role="system", extra={"cat": "flash"})
            rep = await bare_ack_repair(text, list(window), spec)
            if rep:
                speak(rep)
                return (spoken_text + " " + rep).strip()
        elif _ag.a_continuity_claim_over_nothing(text, spoken_text, acted=did_act, anything_running=running):
            # V2-645 — «¿sigues con esa tarea?» answered «sigo con ella» over NOTHING. The correction is the
            # deterministic state sentence, spoken as a follow-up (the lie already sounded; V2-572's shape).
            emit("brain", "🚧 continuidad afirmada sin nada en marcha — digo el estado de verdad",
                 text=text[:160], role="system", extra={"cat": "flash"})
            rep = continuity_truth()
            speak(rep)
            return (spoken_text + " " + rep).strip()
        elif _ag.an_empty_wait_answers_a_question(text, spoken_text, acted=did_act, anything_running=running):
            emit("brain", "🚧 pregunta contestada con una espera VACÍA (nada en marcha) — compongo la "
                 "respuesta que falta", text=text[:160], role="system", extra={"cat": "flash"})
            rep = await empty_wait_repair(text, list(window), spec)
            if rep:
                speak(rep)
                return (spoken_text + " " + rep).strip()
        elif _ag.a_cover_left_hanging(text, spoken_text, covered=covered, acted=did_act):
            emit("brain", "🚧 turno MUDO tras el nexo — compongo el cierre que falta",
                 text=text[:160], role="system", extra={"cat": "flash", "covered": covered})
            rep = await mute_cover_repair(text, list(window), spec)
            if not rep and pick_closer is not None:
                try:
                    rep = pick_closer() or ""
                except Exception:
                    rep = ""
            if rep:
                speak(rep)
                return rep
    except Exception:
        pass
    return spoken_text
