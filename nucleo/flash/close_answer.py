"""His answer to OUR «which one should I close?» carries that question's licence — and only that one (V2-812 T-05).

Measured in a moving car (phone PWA). «Vale, pues aquí no suena nada, cierra el resto de aplicaciones.» → the engine
asked «¿cuál cierro, …?» → he answered «Las dos.». Two words with no close verb: the close the model then called was
refused twice as context-bleed («el operador no ha pedido cerrar nada»), and the same turn resumed the music — the
one thing the answer did not ask for. The question was ours; its answer was read as if it came from nowhere.

Three facts decide, none of them words:

  · a «which one should I close?» is pending — `widgets.instances` remembers the one it asked (`pending_close_ask`);
  · the turn's own brief reads it, surely, as an ANSWER (`request_type`, «the user answers a question WE just asked»);
  · what the turn tries to do is a close (licensed here), or something that STARTS production on a player
    (`runtime.produce`, declared in its manifest) — which an answer to «which one should I close?» never asked for.

Which card(s) the answer means is the existing resolution's (`instances.resolve_close`'s quantifier and title-word
readings: «las dos» → all, a title word → that one), applied over the cards the question offered.
"""
from __future__ import annotations

from loguru import logger


def pending() -> list[str]:
    """The cards the pending «which one should I close?» offered ([] = no such question)."""
    try:
        from widgets import instances as _inst
        return _inst.pending_close_ask()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"close_answer: pending question unread — {e}")
        return []


def answers(brief) -> bool:
    """Does this turn ANSWER a pending «which one should I close?» — by the brief's verdict, never by its words?"""
    if brief is None or not pending():
        return False
    try:
        from nucleo.flash import turn_brief as _tb
        kind, info = _tb.read(brief, _tb.REQUEST_KEY, "")
        return str(kind or "") == "answer" and bool(info and info.get("used"))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"close_answer: brief unread — {e}")
        return False


def targets(text: str, open_ids) -> list[str]:
    """The open cards his answer picks among those the question offered ([] = it picks none, or there was none)."""
    offered = pending()
    if not offered:
        return []
    try:
        from widgets import instances as _inst
        still = [o for o in offered if o in set(str(i) for i in open_ids or [])]
        if not still:
            return []
        if len(still) == 1 or _inst.wants_every(text):
            return still                       # «las dos» / «both» — or only one of them is left to close
        named = _inst._named_by_title(still, text)
        return [named] if named else []
    except Exception as e:  # noqa: BLE001
        logger.debug(f"close_answer: targets unresolved — {e}")
        return []


def refuses(brief, wid: str, action: str) -> bool:
    """True when an answer to «which one should I close?» would START production on `wid` — not what it asked."""
    if not answers(brief):
        return False
    try:
        from widgets import producers
        return producers.starts_production(str(wid or ""), str(action or ""))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"close_answer: producers unread — {e}")
        return False


def _open_now() -> list[str]:
    try:
        from server.voice_api import open_instances
        return [str(i) for i in open_instances() or [] if str(i)]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"close_answer: canvas unread — {e}")
        return []


def backstop(text: str, brief, emit, acted: dict, open_ids=None) -> list[str]:
    """The model called no close on a turn that ANSWERS our «which one should I close?»: close what the answer picks.

    Both channels' post-stream close backstop asks this first. Returns the cards closed ([] = not this case: no
    pending question, the brief does not read an answer, the model already closed, or the answer picks none)."""
    if (acted or {}).get("closed") or not answers(brief):
        return []
    ids = targets(text, _open_now() if open_ids is None else open_ids)
    if not ids:
        return []
    from nucleo.acts import canvas_turn
    from nucleo.acts import canvas
    req = {**canvas_turn.request_of(brief, text), "answered": True}   # `answers(brief)` above: his answer licenses
    ids = [cid for cid in ids if canvas.apply("close", cid, src="flash", emit=emit, request=req)]
    if not ids:
        return []
    for cid in ids:
        try:
            from nucleo.flash import canvas_license as _lic
            _lic.note_operator_close(cid)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"close_answer: close not recorded — {e}")
    acted["widget"] = True
    acted["closed"] = True
    emit("brain", "🙈 close by backstop — his answer to our «which one should I close?»", text=",".join(ids),
         role="system", extra={"cat": "flash", "kind_diag": "close_answer_backstop"})
    try:
        from widgets import instances as _inst
        _inst.clear_close_ask()                # answered
    except Exception as e:  # noqa: BLE001
        logger.debug(f"close_answer: question not cleared — {e}")
    return ids
