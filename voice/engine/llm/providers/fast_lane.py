"""The deterministic fast lane of the VOICE channel (V2-539), extracted from the provider paying the
architecture ratchet (V2-572 crossed its ceiling; the table calls for extracting a cohesive concern, and this
block always was one: everything a turn does when the action map resolves it without a model).

One behavioural change rides the move, and it is the operator's own words (2026-09-03): the lane used to
execute «IN SILENCE», and he asked for the opposite — *«when you tell him to close something or open
something, he has to say 'ok, done'»*. So after the mutation lands, the lane now speaks a short varied ack
(`langs.pick_ack`: «Hecho.» / «Vale, hecho.» / …) out of band through `voice.proactive.speaker()` — the same
mouth the accumulator notices use, because a fast-lane turn never opens an LLM stream to ride. The ack is
spoken AFTER the execute, so it can never promise what did not happen; if the executor declines (live work
behind the widget, V2-567), the turn falls through whole to the model and no ack sounds. Mirror in
`probe.py::run_turn` (parallel impl — its reply carries the same ack for parity).
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger


async def _speak_ack(brain) -> None:
    """Best-effort, never over the operator's voice, varied, anti-echo updated — the filler's own manners."""
    try:
        from voice import proactive
        from voice.engine.core import langs
        speak = proactive.speaker()
        if speak is None or proactive.user_speaking():
            return
        phrase = langs.pick_ack(getattr(brain, "_last_ack", ""))
        if not phrase:
            return
        brain._last_ack = phrase
        try:
            brain._last_spoken = phrase          # anti-echo: the mic must not re-capture it
            brain._last_spoke_at = time.time()
        except Exception:
            pass
        r = speak(phrase)
        if asyncio.iscoroutine(r):
            await r
    except Exception:
        pass


async def handled(brain, text: str, emit, *, first_turn: bool, t_entry: float, window_max: int) -> bool:
    """A KNOWN short command — one utterance bounded by silence — skips the model entirely: exact
    whole-utterance lookup, allowlisted direct action, executed through the same emit funnel the model's own
    output uses, then confirmed out loud. Anything not verbatim-known (a compound sentence, a negation,
    novelty) falls through untouched — when in doubt, the LLM. It runs AFTER the hard interrupt / echo /
    attention gate (safety and directedness first) and BEFORE the accumulator, but only when NO fragment chain
    is pending: a command spoken mid-chain belongs to the chain's merged phrase, and hijacking it out would
    act on half a sentence. Fail-open by construction (the caller catches): any exception and the turn
    proceeds as if the module did not exist."""
    if first_turn:
        return False
    from nucleo import actionmap as _amap
    if not _amap.enabled() or (getattr(brain, "_acc", None) and brain._acc.fragments):
        return False
    _tm = time.time()
    _amap_hit = _amap.match_spoken(text)   # V2-635: a leading «Johnny, …» must not hide a known order
    _amap_ms = round((time.time() - _tm) * 1000, 2)
    if _amap_hit is None or not _amap.execute(_amap_hit, emit, phrase=text):
        return False
    _desc = _amap.describe(_amap_hit)
    # `engine: "actionmap"` is not decoration: the viewer's LAYER column reads exactly this field
    # (`DebugPanel.brainName`) and the Master reads it too. Without it a map turn was painted «FlashBrain» /
    # tagged «LLM» — the timeline claimed the model resolved a turn it never saw, which is the one thing this
    # whole mechanism must not make harder to audit. `origin` is the normalized field both surfaces group and
    # count by.
    emit("actionmap", "⚡ action map: direct action (no model)", text=text[:160], role="user",
         extra={"cat": "flash", "action": _desc, "entry": _amap_hit.get("id"),
                "source": _amap_hit.get("source"), "match_ms": _amap_ms,
                "engine": "actionmap", "origin": "actionmap",
                "pre_ms": round((time.time() - t_entry) * 1000, 1), "src": "actionmap"})
    from nucleo.flash import dialog as _dialog0
    _dialog0.push_user(brain._window, text)
    del brain._window[:-window_max]
    try:
        # Conv buffer (mirror of the provider's post-reply write): the NEXT turn — and a worker's
        # recent-conversation block — must see that this phrase was acted on.
        from memory import api as _memory0
        _memory0.write(f"Operador: {text[:200]} · zaelar: [{_desc}]",
                       kind="conv", level="short", importance=0.2, ttl_days=2.0,
                       meta={"source": "conv", "u": text[:400], "a": f"[{_desc}]"})
    except Exception:
        pass
    try:
        # turn.completed for Susurro (V2-539 §3.5): a fast-path turn stays auditable — without this, the
        # auditor goes blind on exactly the turns most likely to need a correction.
        from voice import observer as _obs0
        _obs0.turn_detail(system="", window=list(brain._window)[-6:], tools=[],
                          user=text,
                          decision={"action": _desc, "actionmap": _amap_hit.get("id")})
    except Exception:
        pass
    # V2-633: the ack now rides the style policy — genesis says a short order runs in SILENCE (the pause IS
    # the answer), superseding V2-572's always-ack; the operator re-enables it by rule («confírmame las
    # órdenes») and it applies on the very next turn.
    try:
        from nucleo import style_policy as _style
        _ack_on = _style.confirm_short_actions()
    except Exception:
        _ack_on = True                      # fail-open to the old behavior: never mute by accident
    if _ack_on:
        await _speak_ack(brain)
    return True


# ── PRESENCE fast lane (V2-640) ──────────────────────────────────────────────────────────────────────────
# «¿Sigues ahí?» is not a task — it is a knock on the door, and answering it through a 3-5 s model turn is
# how the 19:27 session became a dialogue of besugos: the knock armed a thinking filler («Déjame ver…»), the
# operator asked what we wanted to see, and every meta-question armed another cover. A presence check has
# exactly one honest answer and it is knowable without a model: "I'm here" (plus "still on your task" when
# workers are actually running). Whole-utterance match, deterministic, same manners as the action map —
# the model is skipped, the exchange still lands in the window and the conv buffer, and observability says
# `engine: "presence"` so no one audits a model turn that never happened.
# The DETECTOR lives in `nucleo/flash/presence.py` — neutral ground both channels import (this lane
# downward, the probe by injection), so the two can never drift apart on what counts as a knock.
from nucleo.flash.presence import is_presence_check, is_summons  # noqa: F401 — re-exported for the lane's tests


# ── SMALL TALK fast lane (V2-674) ────────────────────────────────────────────────────────────────────────
# The presence knock's wider family: a greeting, «¿qué tal?», «gracias», «adiós». Measured in the operator's
# own English session (sid fdd096a3, 2026-09-11), «Hello and good morning. How are you?» cost a 3.4 s model
# call covered by «Let me explain…» — a lead-in that promises an explanation nobody asked for. The detector
# and the phrasebook live outside this file for the same two reasons presence does: the probe channel needs
# the SAME verdict, and the vocabulary has to be DATA so a fortieth language is a translation.
from nucleo.flash import smalltalk as _smalltalk  # noqa: E402


async def small_talk(brain, text: str, emit, *, first_turn: bool, window_max: int,
                     ask_waiting: bool = False) -> bool:
    """Answer a set phrase instantly, without the model. False = not one → the turn proceeds untouched.

    Fail-open like its siblings. Three gates beyond the phrasebook's own strictness, each closing a way a
    canned answer could swallow something real: never the first turn (the kickoff is not a conversation yet),
    never while a worker's question is pending (a «gracias» then may be the ANSWER to it), and never with no
    mouth to speak with — the chat channel has its own mirror.
    """
    if first_turn or ask_waiting:
        return False
    # A PHASE that guides the conversation outranks the phrasebook (V2-675). During the introduction «hola»
    # is not small talk — it is the first move of a conversation that has somewhere to go, and answering it
    # from a table would end the exchange the phase exists to start. This is the operator's own «excepción
    # al inicio», and it belongs HERE rather than inside the pack: the pack writes prompt, and a lane that
    # never reaches a model would not read it.
    try:
        from nucleo import context_packs
        if context_packs.active_ids():
            return False
    except Exception:  # noqa: BLE001
        pass
    book = {}
    try:
        from voice.engine.core import langs
        book = langs.smalltalk_book()
    except Exception:  # noqa: BLE001
        return False
    if not book:
        return False                       # no phrasebook for this language — the model answers, as before
    bounce = bool(getattr(brain, "_smalltalk_bounce", False))
    # Cleared HERE, on every turn that reaches the lane — not only on the ones it answers. The flag says «the
    # question is still in the air», and any other sentence takes it out of the air; leaving it set would let
    # a «bien» three turns later still be read as an answer to a question nobody remembers asking.
    brain._smalltalk_bounce = False
    intent = _smalltalk.classify(text, book, bounce_pending=bounce,
                                 assistant_names=_presence_names())
    if not intent:
        return False
    try:
        from voice import proactive
        speak = proactive.speaker()
        if speak is None or proactive.user_speaking():
            return False                   # no mouth (chat channel) / talking over — the model answers
    except Exception:  # noqa: BLE001
        return False
    phrase = _smalltalk.reply_for(intent, book, avoid=getattr(brain, "_last_smalltalk", ""))
    if not phrase:
        return False                       # a half-filled pack answers nothing rather than answering wrong
    brain._last_smalltalk = phrase
    # Only a reply that HANDED THE QUESTION BACK makes the next «bien» mean «I'm fine». Set after the reply
    # is chosen and cleared on every other intent, so the window is exactly one exchange wide.
    brain._smalltalk_bounce = _smalltalk.bounces(intent, book)
    try:
        brain._last_spoken = phrase        # anti-echo, the filler's own manners
        brain._last_spoke_at = time.time()
    except Exception:
        pass
    emit("smalltalk", "💬 frase hecha — atendida sin modelo", text=text[:160], role="user",
         extra={"cat": "flash", "engine": "smalltalk", "origin": "smalltalk", "intent": intent,
                "reply": phrase, "src": "smalltalk"})
    # The exchange HAPPENED (V2-605's canned-line lesson): a phrase of ours that skips the history erases its
    # own story, and the next model turn would answer a greeting it has no record of receiving.
    from nucleo.flash import dialog as _dialog2
    _dialog2.push_user(brain._window, text)
    brain._window.append({"role": "assistant", "content": phrase})
    del brain._window[:-window_max]
    try:
        from memory import api as _memory2
        _memory2.write(f"Operador: {text[:200]} · zaelar: {phrase}",
                       kind="conv", level="short", importance=0.1, ttl_days=1.0,
                       meta={"source": "conv", "u": text[:400], "a": phrase})
    except Exception:
        pass
    try:
        from voice import observer as _obs2
        _obs2.turn_detail(system="", window=list(brain._window)[-6:], tools=[],
                          user=text, decision={"action": "smalltalk", "intent": intent, "reply": phrase})
    except Exception:
        pass
    r = speak(phrase)
    if asyncio.iscoroutine(r):
        await r
    return True


def _presence_names() -> tuple[str, ...]:
    """The assistant's own names, so «Johnny, hola» strips down to «hola». Best-effort: the phrasebook must
    not hard-depend on the attention gate (V2-665's lesson about where the authority lives)."""
    try:
        from nucleo.flash.presence import assistant_names
        return tuple(assistant_names())
    except Exception:  # noqa: BLE001
        return ()


async def presence(brain, text: str, emit, *, first_turn: bool, window_max: int) -> bool:
    """Answer a presence knock instantly, without the model. False = not one (or no mouth to speak with) →
    the turn proceeds untouched. Fail-open like `handled` — the caller catches everything."""
    if first_turn:
        return False
    _aname = ""                         # V2-665: `presence.assistant_names()` reads the wake words — see its
    #                                     docstring for why the settings file was the wrong (and empty) source.
    # V2-665 — a bare «Johnny.» is the SAME class: an address with no request in it. Left to the model it
    # answered «Dime, Ricardo.» half the time and INVENTED an errand the other half (session e82f7fcb: it
    # fired a `widget_data` search off a memory pill from the night before). The honest pools already say the
    # right thing, and here they cost no model and reach no tool.
    try:
        from voice.engine.core import langs as _lg_voc
        _vocatives = tuple(_lg_voc.smalltalk_book().get("vocatives") or ())
    except Exception:  # noqa: BLE001
        _vocatives = ()
    _knock = is_presence_check(text, _aname, _vocatives)
    if not (_knock or is_summons(text, _aname)):
        return False
    try:
        from voice import proactive
        speak = proactive.speaker()
        if speak is None or proactive.user_speaking():
            return False                   # no mouth (chat channel) / talking over — the model answers
    except Exception:
        return False
    busy = False
    try:
        from nucleo import dispatch as _d
        busy = _d.has_active()
    except Exception:
        pass
    try:
        from voice.engine.core import langs
        sp = langs.spec()
        pool = list(getattr(sp, "presence_busy" if busy else "presence_idle", ()) or ())
    except Exception:
        pool = []
    if not pool:
        return False
    last = getattr(brain, "_last_presence", "")
    import random as _rnd
    phrase = _rnd.choice([p for p in pool if p != last] or pool)
    brain._last_presence = phrase
    try:
        brain._last_spoken = phrase        # anti-echo, the filler's own manners
        brain._last_spoke_at = time.time()
    except Exception:
        pass
    emit("presence", "🚪 presence knock answered (no model)" if _knock else
         "🙋 llamada por su nombre — atendida sin modelo", text=text[:160], role="user",
         extra={"cat": "flash", "engine": "presence", "origin": "presence", "busy": busy,
                "reply": phrase, "src": "presence", "kind_diag": "knock" if _knock else "summons"})
    # The exchange HAPPENED — it must exist for the next model turn (the canned-line lesson, V2-605:
    # a phrase of ours that skips the history erases its own story).
    from nucleo.flash import dialog as _dialog
    _dialog.push_user(brain._window, text)
    brain._window.append({"role": "assistant", "content": phrase})
    del brain._window[:-window_max]
    try:
        from memory import api as _memory
        _memory.write(f"Operador: {text[:200]} · zaelar: {phrase}",
                      kind="conv", level="short", importance=0.1, ttl_days=1.0,
                      meta={"source": "conv", "u": text[:400], "a": phrase})
    except Exception:
        pass
    try:
        from voice import observer as _obs
        _obs.turn_detail(system="", window=list(brain._window)[-6:], tools=[],
                        user=text, decision={"action": "presence", "reply": phrase})
    except Exception:
        pass
    r = speak(phrase)
    if asyncio.iscoroutine(r):
        await r
    return True
