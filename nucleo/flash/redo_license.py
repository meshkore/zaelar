"""nucleo/flash/redo_license.py — when a re-emitted op is a REDO, not a drag (V2-791).

`data_ops.is_context_bleed` eats a mutation identical to the one that just ran, whose content the turn does not
mention: the model dragging the previous turn's op. This module is its exception for the turns that ask for the op
again, read from structure — never from a phrase table.
"""
from __future__ import annotations

from loguru import logger as _log


def licensed(last, wid: str, said: str, *, brief=None) -> bool:
    """V2-791 — a re-emitted op is a drag only when the previous one LANDED and the turn did not ask for it
    again. Three structural readings, any of which makes the re-emit a REDO that runs:

      · the card itself reported that the previous op did not happen (`widgets/late_report`: a result that
        falsified an agent order on this card after it ran) — it left no effect, so there is nothing to duplicate;
      · his turn NAMES that card as its target (`named_target.names_it`, never a card named to be left alone) —
        «¿lo vas a hacer en el widget de YouTube que estoy viendo?» asks for the op on that card again;
      · the redo verdict says the turn corrects what we just did on that card (`redo_decision.corrects`), when a
        verdict exists — the fix must hold without one, which is why the two readings above need none.

    Measured: `youtube:channel_videos` ran once on a face he could not see, and three re-emits after
    «¿lo vas a hacer en el widget que estoy viendo?», «no estás haciendo nada con el widget» and «quiero que lo
    hagas directamente» were all eaten here as context-bleed. No phrase table: a complaint is read from the card,
    the turn's own target, or the verdict. Never raises; unreadable → not licensed (the guard stands)."""
    try:
        l_ts = float(last[3])
    except (TypeError, ValueError, IndexError) as _e:
        _log.debug(f"redo_license: line 27 failed: {_e!r}")
        return False
    try:
        from widgets import late_report as _late
        if _late.falsified_since(wid, l_ts):
            return True
    except Exception as _e:  # noqa: BLE001
        _log.debug(f"redo_license: line 33 failed: {_e!r}")
        pass
    try:
        from nucleo.flash import named_target as _nt
        if _nt.names_it(said, wid, [wid]):
            return True
    except Exception as _e:  # noqa: BLE001
        _log.debug(f"redo_license: line 39 failed: {_e!r}")
        pass
    try:
        if brief is not None:
            from nucleo.flash import redo_decision as _redo
            if _redo.corrects(brief, str(wid).split("::", 1)[0]):
                return True
    except Exception as _e:  # noqa: BLE001
        _log.debug(f"redo_license: line 46 failed: {_e!r}")
        pass
    return False
