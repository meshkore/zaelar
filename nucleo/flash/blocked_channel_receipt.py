"""The reply that let a blocked channel's link through says so — both channels (V2-604, 2026-10-14).

`video-blocked-channel-respected` (ES and EN 3/5): he blocked Rick Astley, pasted a link from the same channel, and
the video was queued or played — the explicit order wins, which is the rule — but the reply never said the link
came from the channel he had just blocked («it's already loaded, nothing new to start»). He cannot tell whether
the block still holds or whether this is an exception made on purpose.

The video card stamps the fact when its action lets the link through (`widgets.youtube.blocked_order`); this
module reads it — only in a turn whose own orders touched the player (`canvas_focus.this_turn_acts`), consumes it
so it is said once, and owes the sentence unless the reply already speaks of the block. The sentence is the
language's own (`receipt_blocked_channel_*`).
"""
from __future__ import annotations

import asyncio
import re
import time

from loguru import logger

#: A reply that already speaks of the block («bloqueaste», «blocked») owes nothing.
_SAYS_BLOCK = re.compile(r"bloque|block", re.I)
#: The voice rail dispatches detached: how long its stamp may take to land after the words streamed.
VOICE_WAIT_S = 1.2
_POLL_S = 0.1


#: The player acts that can let a pasted link through (a `show` is how `play_video` lands on the card).
_LETS_IN = frozenset({"load", "add", "show"})


def _may_owe() -> bool:
    """Did this turn's own orders load/queue on the player, with some channel blocked? Else nothing is read."""
    try:
        from nucleo import canvas_focus as _cf
        from widgets import store
        ran = any(str(c).split("::", 1)[0] == "youtube" and a in _LETS_IN for c, _k, a in _cf.this_turn_acts())
        return ran and bool((store.load("youtube") or {}).get("blocked_channels"))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"blocked_channel_receipt: turn acts unread — {e}")
        return False


def line_for(reply: str, stamp: dict, lang=None) -> str:
    """The sentence owed for this stamp — "" when there is none or the reply already says it."""
    if not stamp or not stamp.get("channel") or _SAYS_BLOCK.search(str(reply or "")):
        return ""
    if lang is None:
        from i18n import langs as _langs
        lang = _langs.current_language()
    tpl = lang.receipt_blocked_channel_queued if stamp.get("queued") else lang.receipt_blocked_channel_played
    return str(tpl).format(channel=str(stamp["channel"])[:80])


def _emit(line: str, stamp: dict) -> None:
    try:
        from voice.observer import emit
        emit("brain", "⛔ enlace de un canal bloqueado: dicho en la respuesta", text=line[:160], role="system",
             extra={"cat": "flash", "id": "youtube", "channel": stamp.get("channel"), "queued": stamp.get("queued")})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"blocked_channel_receipt: not emitted — {e}")


def owed(reply: str, lang=None) -> str:
    """The sentence this turn's reply owes — consuming the stamp. Never raises."""
    try:
        if not _may_owe():
            return ""
        from widgets.youtube import blocked_order as _bo
        stamp = _bo.take()
        line = line_for(reply, stamp, lang)
        if line:
            _emit(line, stamp)
        return line
    except Exception as e:  # noqa: BLE001
        logger.debug(f"blocked_channel_receipt: skipped — {type(e).__name__}: {e}")
        return ""


def complete(reply: str) -> str:
    """The text channel's reply with the sentence it owes appended."""
    line = owed(reply)
    return f"{str(reply or '').rstrip()} {line}".strip() if line else reply


async def said_after(spoken: str, send, speech) -> str:
    """The voice rail's door: wait briefly for the detached dispatch's stamp, say the owed sentence after the
    streamed words, and return what the turn said in total."""
    try:
        if not _may_owe():
            return spoken
        from widgets.youtube import blocked_order as _bo
        deadline = time.monotonic() + VOICE_WAIT_S
        while not _bo.pending() and time.monotonic() < deadline:
            await asyncio.sleep(_POLL_S)
        line = owed(spoken)
        if not line:
            return spoken
        send(speech.sanitize(line, drop_metadata=False))
        return f"{str(spoken or '').rstrip()} {line}".strip()
    except Exception as e:  # noqa: BLE001 — the turn's words stand; the timeline says the sentence was lost
        logger.debug(f"blocked_channel_receipt: voice line not sent — {e}")
        return spoken
