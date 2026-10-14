"""A turn the operator has not decided is never completed by the engine (V2-781, `tres-tarjetas-y-el-video-por-alusion`).

Measured ES+EN 2026-10-11, the Dune trailer on `youtube` and calm music on `musica`, both playing, and both
declaring `volume_down` and `pause`:

  · EN «hey, turn the volume down a bit» — the screen verdict read `musica:volume_down` at 0.78, under the bar two
    players need (`player_control.PLAYER_SURE`), so the turn ASKED «Which one exactly? I have musica, youtube.» —
    and then the text channel's verdict rung (`direct_action.resolve`, V2-770) turned the music down anyway and
    the question became «Done.».
  · EN «ok leave it. pause that for a sec» — the model itself asked «Which one — the music or the Dune trailer?»,
    called nothing, and the rung paused the VIDEO on a 0.67 verdict. «Done.» again.

The rung is the engine's own inference from the verdict, and it filled a turn that was not empty: it held a
question. Two cases, one rule — the rung does not run when:

  · the turn's words ASK the operator for a detail (`clarifying.asks_for_missing_detail`) — answering it is his;
  · the verdict's card is one of several open cards that declare the same action and `frontend.which_card` (the
    one decision for «whose order is it», with the players' bar) would ASK — unless his words name that card, or
    the card his last turn acted on IS that card (the conversation's subject agrees with the verdict).
"""
from __future__ import annotations

from loguru import logger


def why(brief, widget_id: str, action: str, *, operator_text: str = "", model_words: str = "") -> str:
    """"asked" | "shared" when the verdict's `widget_id:action` must not be run for him, else "". Never raises."""
    try:
        from nucleo.flash import clarifying as _cl, parked_refusal as _parked
        # …unless the reply only REPEATS the card's refusal of the turn before: that question was already asked, and
        # his words this turn are its answer (video-queue ES, 2026-10-11: «Dime a qué posición» said twice).
        # …and a question the VERDICT is sure enough to answer is not the operator's to settle (2026-10-15, his 70%:
        # «en un 70% continuamos»). Live bench E3: «…should I go ahead?» / «do you mean review or book?» over an order
        # read at 1.00 and `mensajeria:forward` at 0.77-0.79 — nothing was sent, 2 runs in 7.
        if model_words and _cl.asks_for_missing_detail(model_words) and not _parked.parrots(model_words, widget_id, action) \
                and not sure_order(brief, widget_id, action):
            return "asked"
        from nucleo.flash import frontend as _fe
        if _fe.which_card(widget_id, action, brief=brief)[0] != "ask":
            return ""
        base = str(widget_id or "").split("::", 1)[0].strip().lower()
        from nucleo.flash import named_target as _nt
        ids = list(brief.get("open_ids") or []) if isinstance(brief, dict) else []
        named = _nt.target(operator_text, ids or _fe._screen_now(), action)
        if named:                       # his words settle it: the verdict's card runs, another card's never does
            return "" if named.split("::", 1)[0].lower() == base else "shared"
        from memory import api as _memapi
        from nucleo import canvas_focus as _cf
        focus = _cf.last_turn_card(list((_memapi.state() or {}).get("open_widgets") or []))
        return "" if focus and focus.split("::", 1)[0].lower() == base else "shared"
    except Exception as e:  # noqa: BLE001
        logger.debug(f"undecided: skipped — {type(e).__name__}: {e}")
        return ""


def sure_order(brief, widget_id: str, action: str) -> bool:
    """Is the turn read as an ORDER, and its action as exactly `widget_id:action`, both at or above the operator's
    `consent.intent_act_at`? The one place a doubt is weighed against his threshold. Never raises."""
    try:
        from nucleo import consent
        from nucleo.flash import turn_brief as _tb
        floor = consent.intent_act_at()
        kind, k_info = _tb.read(brief, _tb.REQUEST_KEY, "", min_confidence=floor)
        target, t_info = _tb.read(brief, _tb.TARGET_KEY, "", min_confidence=floor)
        owner, _sep, name = str(target or "").rpartition(":")
        return bool(k_info and t_info) and str(kind) == "order" and name == action \
            and owner.split("::", 1)[0].lower() == str(widget_id or "").split("::", 1)[0].lower()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"undecided: sure_order skipped — {e}")
        return False


def a_question_holds(brief, words: str) -> bool:
    """Does the reply's question hold the turn's act for him? Only while the verdict is NOT sure of the order and its
    action (`sure_order`, the operator's 70%). The one test both channels' promise repair asks before it runs (live
    bench E3, 2026-10-15: «…what should the message say exactly?» over order 1.00 and `forward` 0.75 — the repair
    never ran and nothing was sent). A question with no verdict, or an unsure one, holds as it always did."""
    from nucleo.flash import clarifying as _cl, direct_action as _da
    if not _cl.asks_for_missing_detail(words or ""):
        return False
    wid, action = _da.from_brief(brief)
    return not (wid and action and sure_order(brief, wid, action))


def stops_the_rung(brief, widget_id: str, action: str, *, operator_text: str = "", model_words: str = "") -> bool:
    """`why`, with its observability line: True when the verdict rung must leave this turn alone."""
    reason = why(brief, widget_id, action, operator_text=operator_text, model_words=model_words)
    if reason:
        try:
            from voice.observer import emit
            emit("brain", "❓ el veredicto NO completa: el turno no está decidido", text=f"{widget_id}:{action} · {reason}",
                 role="system", extra={"cat": "flash", "widget": widget_id, "action": action, "why": reason})
        except Exception as e:  # noqa: BLE001
            logger.debug(f"undecided: emit skipped — {e}")
    return bool(reason)
