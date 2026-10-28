"""What an act of this turn ENDED in, read from the card it touched — the objects the mouth's lines name (refactor2710-03).

`nucleo/turn/reply.py` says one line per verdict; this module reads the facts some verdicts carry, each from the card's
own state, never from our reply's words:

  · a PLAYER control (next / previous / play / pause / add / remove on the video or music card) is `met` with what plays
    now or what the queue holds — or `cannot` when the embedded player refused it (`acts.media.settled`, 2026-10-11);
  · a pasted link from a channel he BLOCKED, let through because he asked, is `met` with the card's stamp (V2-604);
  · a bare acknowledgement over a card whose declared end state still reads unmet is not said as «done» (2026-10-14).

Each returns `reply.Outcome`s whose `said` is the card's own sentence (the card that acted knows what it did).
"""
from __future__ import annotations

import asyncio
import re
import time
import unicodedata

from loguru import logger

MOVES = frozenset({"next", "previous", "play", "play_item", "play_result", "resume"})
PAUSES = frozenset({"pause"})
ADDS = frozenset({"add", "add_results"})
#: A removal from the queue owes what is LEFT in it (2026-10-14: «Done.» over a queue still holding the video he dropped).
REMOVES = frozenset({"remove", "clear_list"})
_PLAYERS = ("youtube", "musica")
#: The player acts that can let a pasted link through (a `show` is how `play_video` lands on the card).
_LETS_IN = frozenset({"load", "add", "show"})
#: The voice rail dispatches detached: how long a card's stamp may take to land after the words streamed.
STAMP_WAIT_S = 1.2
#: Words that name no title: «some calm music» does not name «Focus Music for Work…».
_FILLER = frozenset("official video audio lyric lyrics remaster remastered version feat with the and "
                    "music song songs track playlist".split())


def _outcome(verdict: str, card: str, action: str, said: str):
    from nucleo.turn import reply
    return reply.Outcome(verdict, card, action, said=said)


def _lang():
    return __import__("i18n.langs", fromlist=["x"]).current_language()


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _turn_acts(kind: str = "") -> list[tuple[str, str]]:
    """`(card, action)` of the acts HIS turn ran and the card did not refuse (`canvas_focus.this_turn_acts`), of one
    `kind` when given (`control` for a player's transport)."""
    from nucleo import canvas_focus
    return [(str(c).split("::", 1)[0].strip().lower(), str(a or "").strip())
            for c, k, a in canvas_focus.this_turn_acts() if not kind or k == kind]


def _holding(card: str) -> tuple[str, bool, int]:
    """What the player card holds NOW: `(title, paused, queue_total)`; `("", False, 0)` when unreadable."""
    try:
        from widgets import store
        db = store.load(card) or {}
        if card == "youtube":
            lst = [it for it in (db.get("list") or []) if isinstance(it, dict)]
            pos = int(db.get("pos", -1))
            cur = lst[pos] if 0 <= pos < len(lst) else {}
            return str(db.get("title") or cur.get("title") or "").strip(), bool(db.get("paused")), len(lst)
        yt = db.get("yt") if isinstance(db.get("yt"), dict) else {}
        np_ = db.get("now_playing") if isinstance(db.get("now_playing"), dict) else {}
        title = str(np_.get("title") or yt.get("title") or "").strip()
        artist = str(np_.get("artist") or yt.get("artist") or "").strip()
        if artist and title and _norm(artist) not in _norm(title):
            title = f"{artist} — {title}"
        paused = bool(yt.get("paused")) if yt else (np_.get("playing") is False)
        return title, paused, len(yt.get("queue") or [])
    except Exception as e:  # noqa: BLE001
        logger.debug(f"reply_receipts: {card} unread — {e}")
        return "", False, 0


def _queue_line(card: str, total: int, lang) -> str:
    """What the queue holds now: empty, its titles when they are three or fewer, else its count."""
    if not total:
        return str(lang.receipt_queue_empty)
    titles: list[str] = []
    try:
        from widgets import store
        if card == "youtube" and total <= 3:
            titles = [str(it.get("title") or "")[:60] for it in (store.load(card) or {}).get("list") or []
                      if isinstance(it, dict) and str(it.get("title") or "").strip()]
    except Exception as e:  # noqa: BLE001 — the count alone is still true
        logger.debug(f"reply_receipts: queue titles unread — {e}")
    if titles and len(titles) == total:
        joined = "«" + f"» {lang.receipt_and} «".join(titles) + "»" if len(titles) < 3 else \
            "«" + "», «".join(titles[:-1]) + f"» {lang.receipt_and} «{titles[-1]}»"
        return str(lang.receipt_queue_titles).format(total=total, titles=joined)
    return str(lang.receipt_queue_total).format(total=total)


def names_title(said: str, title: str) -> bool:
    """Did what was said carry a distinctive word of the card's title (4+ letters, not a filler)? A comparison with
    the card's data, never a table of our words."""
    t = _norm(said)
    words = {w for w in re.findall(r"[a-z0-9]{4,}", _norm(title)) if w not in _FILLER}
    return bool(t) and any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", t) for w in words)


def player_owed(said: str, controls, lang=None) -> list:
    """`met` with what the player holds now, for the first control the words did not already answer."""
    lang = lang or _lang()
    for card, act in controls or []:
        if card not in _PLAYERS:
            continue
        title, _paused, total = _holding(card)
        if act in MOVES and title and not names_title(said, title):
            return [_outcome("met", card, act, str(lang.receipt_now_playing).format(title=title[:90]))]
        if act in PAUSES and title and not names_title(said, title):
            return [_outcome("met", card, act, str(lang.receipt_paused).format(title=title[:90]))]
        if act in ADDS | REMOVES and (total or act in REMOVES) \
                and not re.search(r"(?<!\d)" + str(total) + r"(?!\d)", str(said or "")):
            return [_outcome("met", card, act, _queue_line(card, total, lang))]
    return []


def _refused_line(out: dict, lang) -> str:
    refused = [t[:90] for t in (out.get("refused") or ([out.get("title")] if out.get("title") else []))]
    if out.get("state") == "blocked" and refused:
        return str(lang.receipt_cannot_play).format(title=f"» {lang.receipt_and} «".join(refused))
    if out.get("state") == "swapped" and out.get("title") and out.get("to"):
        return str(lang.receipt_swapped).format(title=str(out["title"])[:90], to=str(out["to"])[:90])
    return ""


async def player(said: str, controls=None, lang=None) -> list:
    """The player's receipt for this turn's controls: a move the embedded player REFUSED is `cannot` (or a swap, `met`
    with what plays instead) even over words that named the title — they claimed it was playing; else `player_owed`."""
    try:
        controls = _turn_acts("control") if controls is None else controls
        if not any(c in _PLAYERS for c, _a in controls):
            return []
        lang = lang or _lang()
        if any(c == "youtube" and a in MOVES for c, a in controls):
            from nucleo.acts import media as _media
            out = await _media.settled("youtube", min_wait=0.3)
            if (line := _refused_line(out, lang)):
                return [_outcome("cannot" if out.get("state") == "blocked" else "met", "youtube", "move", line)]
        return player_owed(said, controls, lang)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"reply_receipts: player receipt skipped — {type(e).__name__}: {e}")
        return []


async def blocked_channel() -> list:
    """A link from a channel he blocked, let through by HIS order this turn: the card's stamp, said once (V2-604)."""
    try:
        from widgets import store
        from widgets.youtube import blocked_order
        ran = any(c == "youtube" and a in _LETS_IN for c, a in _turn_acts())
        if not ran or not (store.load("youtube") or {}).get("blocked_channels"):
            return []
        deadline = time.monotonic() + STAMP_WAIT_S
        while not blocked_order.pending() and time.monotonic() < deadline:
            await asyncio.sleep(0.1)
        stamp = blocked_order.take()
        if not stamp or not stamp.get("channel"):
            return []
        lang = _lang()
        tpl = lang.receipt_blocked_channel_queued if stamp.get("queued") else lang.receipt_blocked_channel_played
        line = str(tpl).format(channel=str(stamp["channel"])[:80])
        __import__("voice.observer", fromlist=["x"]).emit("brain", "⛔ enlace de un canal bloqueado: dicho en la respuesta", text=line[:160], role="system",
             extra={"cat": "flash", "id": "youtube", "channel": stamp.get("channel"), "queued": stamp.get("queued")})
        return [_outcome("met", "youtube", "blocked_channel", line)]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"reply_receipts: blocked channel skipped — {type(e).__name__}: {e}")
        return []


def end_state_unmet(cards: set[str] | None = None, said: str = "") -> dict | None:
    """The first end state still owed on `cards` (any card when None) that reads NOT met now. With `said`, only the end
    states THIS sentence owes: one another request left open is its business (demo sandbox 2026-10-28, C2/C3)."""
    from nucleo.circuit import spec, verify
    mine = _norm(said)
    for e in spec.open_specs():
        card = str(e.get("target") or "").split(":", 1)[0]
        if card in ("", "desktop", "canvas") or (cards is not None and card not in cards):
            continue
        if mine and _norm(e.get("text")) not in ("", mine):
            continue
        if verify.check(e.get("done_when")) is False:
            return e
    return None


def bare_ack(ack: str, cards: set[str] | None, *, beside: bool = False, said: str = "") -> str:
    """The bare acknowledgement WE are about to say over a turn's writes, or the true line instead: «just started» when
    an errand runs beside it, «not on the card yet» when an end state THIS turn owes on those cards still reads unmet."""
    try:
        lang = _lang()
        if beside:
            return str(lang.done_just_started)
        return str(lang.done_not_on_card) if end_state_unmet(cards, said) else ack
    except Exception as e:  # noqa: BLE001 — an unreadable screen leaves the ack as it was
        logger.debug(f"reply_receipts: ack not checked — {e}")
        return ack
