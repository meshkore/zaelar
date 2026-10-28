"""The lines the mouth says when a turn has nothing of its own to say (refactor2710-06 T-06, from `reminder_guards`).

A turn whose only content is «the task is still running» (`holding_line`), one that came back mute (`mute_backstop`),
and a false delivery claim (`follow_up_line`). Each rotates instead of repeating — «Vale, dame un momento que lo miro.»
was measured four times word for word, «Perdona, ¿me lo repites?» four times in ninety seconds — never claims a step,
and never claims work that is not happening. Every sentence comes from the language table.
"""
from __future__ import annotations

from loguru import logger


def _note(what: str) -> None:
    logger.debug(f"wait_lines: {what}")


def _lang(lang=None):
    from i18n import langs as _langs
    return lang or _langs.current_language()


def _recent(window) -> list[str]:
    said = [str((m or {}).get("content") or "").strip() for m in (window or []) if (m or {}).get("role") == "assistant"]
    return [t for t in said[-3:] if t]


def _longest_pending_min() -> int:
    """Minutes of the longest-running background task, or 0 when that cannot be read. A FACT, not a step."""
    try:
        from nucleo import dispatch as _d
        return max((int(t.get("secs") or 0) for t in _d.pending_summaries()), default=0) // 60
    except Exception as e:  # noqa: BLE001
        _note(f"no pending work read ({e!r})")
        return 0


def holding_line(window, lang=None, after_filler: str = "") -> str:
    """The wait line for a turn whose only content is «still running»: a fresh variant while there is one, and from
    the third consecutive wait the one honest fact — how long it has been. A lead-in filler that already sounded
    burns the opener, so the line CONTINUES it (session 2bdc67ee). The worker chain asleep: no wait line is true."""
    try:
        lang = _lang(lang)
    except Exception as e:  # noqa: BLE001
        _note(f"no language ({e!r})")
        return "Sigo con ello."
    from nucleo.workers import quota_wait as _qw
    if asleep := _qw.asleep_line(window, lang):
        return asleep
    lines = tuple(getattr(lang, "holding_lines", ()) or (getattr(lang, "filler_holding", "Sigo con ello."),))
    recent = _recent(window) + ([lines[0]] if after_filler else [])
    if sum(1 for t in recent if t in lines) >= 2 and (mins := _longest_pending_min()) >= 1:
        waited = str(getattr(lang, "filler_waited", "") or lines[-1]).format(min=mins)
        if not recent or waited != recent[-1]:
            return waited
    return next((ln for ln in lines if ln not in recent), None) \
        or next((ln for ln in lines if not recent or ln != recent[-1]), lines[-1])


def mute_line(window, lang=None) -> str:
    """The line for a turn that came back EMPTY with nothing running: it owns the fault (the model returned nothing,
    not him), rotates, and once every variant was said, says that this is not working (V2-603)."""
    try:
        lang = _lang(lang)
    except Exception as e:  # noqa: BLE001
        _note(f"no language ({e!r})")
        return "Perdona, se me ha ido. ¿Me lo dices otra vez?"
    lines = tuple(getattr(lang, "mute_lines", ()) or ("Perdona, ¿me lo repites?",))
    recent = _recent(window)
    return next((c for c in lines if c not in recent), None) or str(getattr(lang, "mute_stuck", "") or lines[-1])


def _still_working(window, lang) -> str:
    """«Still on it» — unless the worker chain is asleep, where it would be a lie (2026-10-11)."""
    from nucleo.workers import quota_wait as _qw
    return _qw.asleep_line(window, lang) or str(getattr(lang, "filler_still_working", "") or "Sigo con ello.")


def mute_backstop(window, lang, has_work: bool, operator_text: str = "") -> str:
    """The whole decision for a mute turn: live work ABOUT this → «still on it»; nothing → `mute_line`. An ack asks for
    nothing new, so the live work is it (V2-781); work about something else is not this turn's (demo pass C2)."""
    if has_work and operator_text:
        try:
            from voice import endpointing as _ep
            if _ep.is_backchannel(operator_text):
                return _still_working(window, lang)
            from nucleo import dispatch as _d
            from nucleo.flash import router_guards as _rgd
            if _rgd.nothing_running_for(operator_text, [str(r.get("request") or r.get("goal") or "")
                                                        for r in _d.pending_summaries()]):
                has_work = False
        except Exception as e:  # noqa: BLE001
            _note(f"live work unread ({e!r})")
    if not has_work and operator_text and not any(c.isalnum() for c in operator_text):
        return str(getattr(lang, "mute_wordless", "") or mute_line(window, lang))   # «👋» asked for nothing
    return _still_working(window, lang) if has_work else mute_line(window, lang)


def holding_line_now(window, prev_pending: bool = False, *, after_filler: bool = False) -> str:
    """`holding_line` with the language resolved here; a NEW errand after a lead-in filler says it was taken."""
    try:
        lang = _lang()
        taken = str(getattr(lang, "filler_errand_taken", "") or "")
        if after_filler and not prev_pending and taken and taken not in _recent(window):
            return taken
        return holding_line(window, lang, after_filler=after_filler)
    except Exception as e:  # noqa: BLE001
        _note(f"holding line failed ({e!r})")
        return "Sigo con ello." if prev_pending else "Vale, dame un momento."


def follow_up_line(english: bool | None = None) -> str:
    """The honest follow-up over a FALSE delivery claim (V2-660): the missing truth, said late, from the table."""
    from i18n import langs as _lg
    if english is None:
        try:
            english = str(_lg.current_code() or "").lower().startswith("en")
        except Exception as e:  # noqa: BLE001
            _note(f"no language code ({e!r})")
            english = False
    return _lg.spec("en" if english else None).not_on_screen_yet
