"""«Exit full screen» with nothing at full screen is answered as that, never «Done.» (2026-10-14).

`video-exit-fullscreen-unnamed__us` (2/5): the canvas was empty in every turn, `fullscreen_widget(mode=off)` resolved
no card (`show_target.fullscreen_target` returns "" when the canvas reports nothing maximized — on purpose, so an
exit never toggles a card INTO full screen), the turn became `canvas:unfullscreen:` with an empty target, and the
reply was the generic ack «Done.» over an exit that had nothing to act on. He answered «still full screen on my
end, nothing changed».

The fact is the engine's own: no target, no card the canvas reports maximized, and none his own order put there
(`canvas_focus.ordered_fullscreen`). Then a content-free reply is replaced by the language's `fullscreen_nothing`.
A reply with content is left alone — the model may already have said it, or said something truer.
"""
from __future__ import annotations

from loguru import logger

_ACTION = "canvas:unfullscreen:"


def nothing_at_full_screen(action: str) -> bool:
    """Did this turn's exit find NO card at full screen?"""
    a = str(action or "")
    if not a.startswith(_ACTION) or a[len(_ACTION):].strip():
        return False
    try:
        from memory import api as _memapi
        from nucleo import canvas_focus as _cf
        return not str((_memapi.state() or {}).get("maximized_widget") or "").strip() and not _cf.ordered_fullscreen()
    except Exception as e:  # noqa: BLE001 — an unread canvas proves nothing either way
        logger.debug(f"fullscreen_nothing: canvas unread — {e}")
        return False


def honest(reply: str, action: str, lang=None) -> str:
    """The reply, with a content-free ack over an exit that found nothing replaced by the line that says so."""
    try:
        from nucleo.flash import card_receipt as _cr
        if not nothing_at_full_screen(action) or not _cr.content_free(reply):
            return reply
        if lang is None:
            from i18n import langs as _langs
            lang = _langs.current_language()
        return str(lang.fullscreen_nothing)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"fullscreen_nothing: skipped — {type(e).__name__}: {e}")
        return reply


#: The turns (by trace) whose exit found nothing at full screen. Keyed by the turn's trace, not a ContextVar: the tool
#: runs inside the stream's pump task, and what it sets there never reaches the task that closes the turn.
_NOTHING: set = set()


def _trace() -> str:
    try:
        from voice import trace
        return trace.current() or ""
    except Exception as e:  # noqa: BLE001
        logger.debug(f"fullscreen_nothing: no trace for this turn — {e!r}")
        return ""


def note_nothing() -> None:
    _NOTHING.add(_trace())


def said_after(spoken: str, send, speech) -> str:
    """The voice turn's half: its words have already streamed, so a content-free ack over an exit that found nothing
    (`note_nothing`, set by `show_target.fullscreen_dispatch`) gets the honest line AFTER it. Returns the turn's
    spoken text with the line added, for the window."""
    try:
        from nucleo.flash import card_receipt as _cr
        found_nothing = _trace() in _NOTHING
        _NOTHING.discard(_trace())
        if not found_nothing or not _cr.content_free(spoken or ""):
            return spoken
        from i18n import langs as _langs
        line = str(_langs.current_language().fullscreen_nothing)
        send(speech.sanitize((" " if (spoken or "").strip() else "") + line, drop_metadata=False))
        return f"{spoken or ''} {line}".strip()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"fullscreen_nothing: not said — {type(e).__name__}: {e}")
        return spoken
