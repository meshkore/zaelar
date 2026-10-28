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


async def recall_answer(text: str, query: str, spec, sanitize=None) -> str:
    """The recall two-pass route's spoken answer (probe channel): memory block → 1-3 natural sentences.
    Returns "" on any failure — the caller keeps its original reply. `sanitize` is the caller's own
    post-processor (the probe passes speech+dialog's), so this module never reaches into the motor for one —
    the dependency-direction ratchet (7.32) caught exactly that import here on its second day of life."""
    try:
        from nucleo.flash import dialog, recall_heuristics as _rh
        from nucleo.turn.prompt import builder as _prompt
        rblock, _ = await asyncio.to_thread(_prompt.compose_recall, query)
        if not (rblock or "").strip() and _rh.names_thread_position(text):
            # fix02, SAME rule as the voice half above and no wider (review 2026-09-20): the turn points at
            # the LIVE thread and the pills came back empty, so composing from that void only manufactures
            # a refusal — the caller keeps its original reply instead.
            # It is gated on the classifier ON PURPOSE. Ungated, ANY empty recall kept the model's first
            # reply, and that reply was written BEFORE the memory was consulted: on «¿qué talla uso?» with
            # nothing remembered, the honest "no tengo ese dato" the compose produces was being replaced by
            # whatever the model had already improvised — the invention this whole seam exists to prevent.
            return ""
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
        from nucleo.flash import dialog
        from nucleo.turn.prompt import builder as _prompt
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
        from nucleo.flash import dialog
        from nucleo.turn.prompt import builder as _prompt
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
        from nucleo.flash import dialog
        from nucleo.turn.prompt import builder as _prompt
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


def _lang_text(spec, name: str) -> str:
    """A sentence from the operator's LANGUAGE table. `spec` in this module is two things at once: the tests hand
    in a `LangSpec`, the live voice turn hands in the MODEL spec (it is what `collect` needs) — which has none of
    these fields, so in production `getattr(spec, "promise_retracted", "")` was always "" and the honest
    retraction never sounded (demo pass 2026-09-28, Z1: «Let me check your day for tomorrow.» and then silence).
    The table of the configured language is the source; the one handed in only wins when it IS a table."""
    got = getattr(spec, name, "")
    if isinstance(got, str) and got:
        return got
    try:
        from i18n import langs as _langs
        return str(getattr(_langs.current_language(), name, "") or "")
    except Exception:  # noqa: BLE001
        return ""


async def _card_the_catalogue_names(operator_text: str, wait_s: float = 3.0) -> str:
    """The card a question is about when neither it nor the promise NAMES one — asked of the same catalogue reader
    the brief uses (`catalog_widget`), bounded. Demo pass 2026-09-28, Z1: «what's on my plate tomorrow» → «Let me
    check your day for tomorrow.» and no read; neither sentence says «calendar», so the repair found nothing to
    read. Which card holds tomorrow is a question of meaning, not of words: the reader answers it. "" when unsure."""
    try:
        from nucleo import jev as _jev
        from nucleo.flash import card_commission as _cc     # one question per sentence, its answer shared (V2-794)
        from widgets import runtime
        if not (operator_text or "").strip():
            return ""
        cat, conf = await asyncio.to_thread(_cc.late_catalogue, operator_text, wait_s=wait_s)
        cat = cat.split(":")[0]
        if cat and cat != "none" and conf >= _jev.MIN_CONFIDENCE and runtime.get(cat) is not None:
            return cat
    except Exception:  # noqa: BLE001
        pass
    return ""


async def promise_repair(operator_text: str, reply: str, window: list, spec, emit, channel: str = "") -> str:
    """The fourth sibling (V2-717): the reply PROMISED to look («Let me check your Telegram…») and the turn
    looked at nothing. The repair is the look itself, not a better sentence: the widget the promise NAMES is
    read through the seam `read_widget` already owns (`widget_read.prepare` — resolve, read, observe,
    compose) and the operator's sentence is the question. That is what the model should have called, so the
    turn ends with the thing it said it was doing. Returns "" when the promise names no widget we can read,
    or the read comes back empty — the caller then speaks the deterministic retraction, because a promise
    that stays in the air is the one outcome that cannot happen."""
    try:
        from nucleo.flash import dialog, widget_read as _wread
        from nucleo.turn.prompt import builder as _prompt
        # HIS sentence is the order; the reply only echoes it, and can name more than one card (full38 Z1: «what's
        # on my plate tomorrow» → «let me pull up your day and your messages» read the MESSAGES). His words first,
        # then the catalogue on his words, and the reply's naming last.
        wid = _wread.resolve("", operator_text or "") or await _card_the_catalogue_names(operator_text)
        if not wid:
            wid = _wread.resolve("", reply or "")
        if not wid:
            return ""
        sys2 = await _wread.prepare({"widget_id": wid, "question": operator_text}, operator_text,
                                    _prompt._lang_lock(), emit, channel=channel)
        raw = await collect(sys2, operator_text, spec, max_tokens=220)
        return dialog.sanitize_reply(raw).strip()
    except Exception:  # noqa: BLE001
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
        # V2-677 — FIRST, because a denial is worse than a hollow answer: a hollow answer is unhelpful, a
        # denial teaches the operator the product cannot do something it does. It is not composed by a model
        # either — what has to be said is a FACT about this system, so it comes from the language table.
        if _ag.a_reply_denies_the_screen(spoken_text):
            emit("brain", "🪟 negó una capacidad de pantalla que SÍ tiene — lo corrijo",
                 text=spoken_text[:160], role="system", extra={"cat": "flash"})
            rep = _lang_text(spec, "screen_denied_repair")
            if rep:
                speak(rep)
                return (spoken_text + " " + rep).strip()
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
        elif _ag.a_promise_left_hanging(text, spoken_text, acted=did_act, anything_running=running):
            # V2-717 — «Let me check your Telegram…» over NOTHING, three turns in a row (session c502d3ff).
            # The repair is the look the sentence promised; failing that, the honest retraction — never air.
            emit("brain", "🚧 prometió mirar y no miró — hago la lectura que dijo, o lo retiro",
                 text=spoken_text[:160], role="system", extra={"cat": "flash"})
            rep = await promise_repair(text, spoken_text, list(window), spec, emit, channel="voice")
            if not rep:
                rep = _lang_text(spec, "promise_retracted_busy" if running else "promise_retracted") or ""
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


async def answered_from_state(verdict: dict | None, operator_text: str, window: list, spec) -> str:
    """The answer a commission was annulled FOR (`escalation_guard.ANSWERED`): his question, composed from the turn's
    own state — the clock line, the request record (recent and the days before), what is running — and the
    conversation, with the model the turn already pays (2026-10-21). When the state does not hold what he asks, it
    says so the way a person would — naming the day or the thing — and offers to look further, instead of a worker
    hunting for minutes. Returns "" for any other verdict or on failure; the caller keeps what it had."""
    if not verdict or verdict.get("disposition") != "answered":
        return ""
    try:
        from nucleo.flash import dialog
        from nucleo.turn.prompt import builder as _prompt
        ctx = "\n".join(f"{m.get('role', '?')}: {str(m.get('content', ''))[:300]}"
                        for m in (window or [])[-8:] if isinstance(m, dict))
        sys2 = (_prompt._lang_lock()
                + "\nEl operador ha hecho una PREGUNTA que se contesta con lo que ya tienes: tu ESTADO (abajo) y la "
                  "conversación. Contéstala AHORA, en 1-3 frases habladas y naturales, con esos datos. Si pregunta "
                  "por un día, sitúalo (qué día de la semana y qué fecha es) y di lo que hubo; si el estado no tiene "
                  "lo que pregunta, dilo nombrando el día o la cosa y ofrece mirar otra fecha o buscarlo — nunca "
                  "prometas que ya estás en ello.\n\n"
                + f"ESTADO:\n{_prompt.live_state()}\n\nPREGUNTA DEL OPERADOR: {operator_text}"
                + ("\n\nCONVERSACIÓN RECIENTE:\n" + ctx if ctx else ""))
        raw = await collect(sys2, operator_text, spec, max_tokens=240)
        return dialog.sanitize_reply(raw).strip()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"answered_from_state: {e}")
        return ""


async def speak_answered_from_state(verdict: dict | None, operator_text: str, window: list, spec, *, send, spoken: list,
                                    said: str = "") -> str:
    """`answered_from_state`, said: the voice turn's one call, so the turn keeps a single branch for it.

    Returns the turn's reply as it now stands — `said` plus the answer (V2-820 T-06). The caller read its reply before
    this pass; kept stale, a turn whose model only called the tool stayed «mute», the annulled commission no longer
    counted as handled, and the mute backstop glued «Perdona, se me ha ido» after the answer just composed (a live
    session, 2026-10-27). What was said is the reply, whoever composed it."""
    if ans := await answered_from_state(verdict, operator_text, window, spec):
        send(ans)
        spoken.append(" " + ans)
        return "".join(spoken).strip() or said
    return said
