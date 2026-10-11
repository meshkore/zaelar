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
        from nucleo.flash import clarifying as _cl
        if model_words and _cl.asks_for_missing_detail(model_words):
            return "asked"
        from nucleo.flash import frontend as _fe
        if _fe.which_card(widget_id, action, brief=brief)[0] != "ask":
            return ""
        base = str(widget_id or "").split("::", 1)[0].strip().lower()
        from nucleo.flash import direct_action as _da
        if any(str(c).split("::", 1)[0].lower() == base for c in _da.named_cards(operator_text)):
            return ""
        from memory import api as _memapi
        from nucleo import canvas_focus as _cf
        focus = _cf.last_turn_card(list((_memapi.state() or {}).get("open_widgets") or []))
        return "" if focus and focus.split("::", 1)[0].lower() == base else "shared"
    except Exception as e:  # noqa: BLE001
        logger.debug(f"undecided: skipped — {type(e).__name__}: {e}")
        return ""


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
