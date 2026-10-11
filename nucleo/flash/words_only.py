"""A turn the verdict SURELY reads as «tell me» does not get an UNSURE action completed into it.

Measured in `build-a-video-playlist-from-links__us` (2026-10-11, turn 4): «did you actually skip it? what's playing
now» — `request_type = question` 0.99, `wants_words = tell` 1.00, `screen_action = youtube:next` **0.54**. The model
called nothing; the verdict completion (`direct_action.names_an_order` → `resolve`) ran `youtube:next` a second
time, the player was already on the last item, and the reply became «I couldn't: There are no more videos in the
list.» — a false report over a question, which the model then believed for two turns («the list only has PSY»).

This is the same shape the completion already refuses on the other side: a weaker reader may not overrule a
stronger one. `question` is deliberately NOT a veto by itself (V2-757: a polite order is shaped like a question,
and «¿Me pones el siguiente?» reads `next` 0.75). What tells the two apart is the WORDS question: a polite order
answers `act`, a real question answers `tell` — and only when `tell` is SURE and the action is NOT does the
completion stand down. A sure action («¿Puedes parar el vídeo?» → `pause` 1.00) still runs whatever the words
reader says.
"""
from __future__ import annotations

#: The words reader has to be at least this sure that he only wants to be told something.
TELL_FLOOR = 0.9
#: …and the action reader less sure than this for the veto to apply — a sure action is never vetoed.
ACTION_FLOOR = 0.8


def tell_vetoes_unsure_action(brief, *, tell_floor: float = TELL_FLOOR, action_floor: float = ACTION_FLOOR) -> bool:
    """True when the verdict SURELY says «tell me» and the action it names is below the sure floor. Never raises;
    an unreadable brief vetoes nothing (today's path)."""
    try:
        from nucleo.flash import turn_brief as _tb
        words, winfo = _tb.read(brief, _tb.WORDS_KEY, "", min_confidence=tell_floor)
        if winfo is None or not winfo.get("used") or str(words or "") != "tell":
            return False
        _choice, ainfo = _tb.read(brief, _tb.TARGET_KEY, "", min_confidence=action_floor)
        return ainfo is not None and not ainfo.get("used")
    except Exception:  # noqa: BLE001
        return False
