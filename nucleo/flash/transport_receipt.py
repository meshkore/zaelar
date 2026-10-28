"""The TRANSPORT receipt: a reply that ignored the next/previous/play/pause/add he asked for names what happened.

Measured in `build-a-video-playlist-from-links__us` (2026-10-11, turn 3): «I'm Sam, I'm in Austin. anyway skip to
the next one» — `youtube:next` ran, the player moved to PSY, and the reply was «Got it, Sam — Austin it is.» He had
to ask «did you actually skip it? what's playing now». `card_receipt` (V2-781) accounts for CARDS a turn changed and
replaces content-free acks («Done.»); it cannot see that a reply with content answered the side remark and skipped
the order. This module reads the same two facts — what the turn RAN (never what the model says it did) and what the
card HOLDS now — and appends the one sentence owed:

  · a move or a play (`next`, `previous`, `play`, `play_item`, `play_result`, `resume`) → what is playing now;
  · a `pause` → what was paused;
  · an `add`, a `remove` or a `clear_list` → what the queue holds now (its titles when three or fewer).

A reply that already names the title (any distinctive word of it) owes nothing; a failed op owes nothing here (its
failure is named by `widget_data_turn.ensure_failure_named`). The sentences are the language's own (`receipt_*`).
Both channels call it: the text channel beside `card_receipt.complete_probe`, the voice channel after its words
have streamed — there it is said as one more sentence, never a replacement.
"""
from __future__ import annotations

import re
import unicodedata

from loguru import logger

#: Transport actions and the receipt each one owes.
MOVES = frozenset({"next", "previous", "play", "play_item", "play_result", "resume"})
PAUSES = frozenset({"pause"})
ADDS = frozenset({"add", "add_results"})
#: A removal from the queue owes what is LEFT in it (2026-10-14: «Done.» over a queue still holding the video he dropped).
REMOVES = frozenset({"remove", "clear_list"})
#: The player cards and how each one says what it holds: `(title, paused, queue_total)` from its store.
_CARDS = ("youtube", "musica")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _holding(card: str) -> tuple[str, bool, int]:
    """What the player card holds NOW: `(title, paused, queue_total)`; `("", False, 0)` when unreadable."""
    try:
        from widgets import store as _st
        db = _st.load(card) or {}
        if card == "youtube":
            lst = [it for it in (db.get("list") or []) if isinstance(it, dict)]
            pos = int(db.get("pos", -1))
            cur = lst[pos] if 0 <= pos < len(lst) else {}
            title = str(db.get("title") or cur.get("title") or "").strip()
            return title, bool(db.get("paused")), len(lst)
        if card == "musica":
            yt = db.get("yt") if isinstance(db.get("yt"), dict) else {}
            np_ = db.get("now_playing") if isinstance(db.get("now_playing"), dict) else {}
            title = str(np_.get("title") or yt.get("title") or "").strip()
            artist = str(np_.get("artist") or yt.get("artist") or "").strip()
            if artist and title and _norm(artist) not in _norm(title):
                title = f"{artist} — {title}"
            paused = bool(yt.get("paused")) if yt else (np_.get("playing") is False)
            return title, paused, len(yt.get("queue") or [])
    except Exception as e:  # noqa: BLE001
        logger.debug(f"transport_receipt: {card} unread — {e}")
    return "", False, 0


def _queue_line(card: str, total: int, lang) -> str:
    """What the queue holds now: empty, its titles when they are three or fewer, else its count."""
    if not total:
        return str(lang.receipt_queue_empty)
    titles: list[str] = []
    try:
        from widgets import store as _st
        if card == "youtube" and total <= 3:
            titles = [str(it.get("title") or "")[:60] for it in (_st.load(card) or {}).get("list") or []
                      if isinstance(it, dict) and str(it.get("title") or "").strip()]
    except Exception as e:  # noqa: BLE001 — the count alone is still true
        logger.debug(f"transport_receipt: queue titles unread — {e}")
    if titles and len(titles) == total:
        joined = "«" + f"» {lang.receipt_and} «".join(titles) + "»" if len(titles) < 3 else \
            "«" + "», «".join(titles[:-1]) + f"» {lang.receipt_and} «{titles[-1]}»"
        return str(lang.receipt_queue_titles).format(total=total, titles=joined)
    return str(lang.receipt_queue_total).format(total=total)


def names_title(reply: str, title: str) -> bool:
    """Does the reply carry any distinctive word of the title (4+ letters, not a filler)? Then it named it."""
    t = _norm(reply)
    words = {w for w in re.findall(r"[a-z0-9]{4,}", _norm(title)) if w not in _FILLER}
    return bool(t) and any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", t) for w in words)


#: Words that name no title: «some calm music» does not name «Focus Music for Work…».
_FILLER = frozenset("official video audio lyric lyrics remaster remastered version feat with the and "
                    "music song songs track playlist".split())


def owed(reply: str, ops, lang=None) -> str:
    """The sentence a reply still owes for the transport ops the turn ran — "" when none. `ops` is
    `[(card, action)]` of SUCCESSFUL ops. Never raises."""
    try:
        if lang is None:
            from i18n import langs as _langs
            lang = _langs.current_language()
        for card, act in ops or []:
            base = str(card or "").split("::", 1)[0].strip().lower()
            a = str(act or "").strip()
            if base not in _CARDS:
                continue
            title, paused, total = _holding(base)
            if a in MOVES and title and not names_title(reply, title):
                return str(lang.receipt_now_playing).format(title=title[:90])
            if a in PAUSES and title and not names_title(reply, title):
                return str(lang.receipt_paused).format(title=title[:90])
            if a in ADDS | REMOVES and (total or a in REMOVES) \
                    and not re.search(r"(?<!\d)" + str(total) + r"(?!\d)", str(reply or "")):
                return _queue_line(base, total, lang)
        return ""
    except Exception as e:  # noqa: BLE001
        logger.debug(f"transport_receipt: skipped — {type(e).__name__}: {e}")
        return ""


def ops_of_probe(action: str, parte) -> list[tuple[str, str]]:
    """The text channel's successful data-ops, from `widget_data_turn.execute`'s report (`ops` = what ran) — and a
    `play_music` that started (`music_turn.execute`'s report): `play-music-and-build-playlist__us` (2026-10-14)
    answered «I'll put something calm on for you.» 0.6 s AFTER the rail had it playing, so the only reply he got
    promised in the future what had already happened and never said what was on. The voice channel needs no copy:
    there the audio itself is the receipt."""
    if not isinstance(parte, dict):
        return []
    if str(action or "") == "music":
        played = parte.get("executed") == "play_music" and parte.get("ok") is True
        return [("musica", str(parte.get("accion") or "play"))] if played else []
    if str(action or "") != "widget_data":
        return []
    return [(str(o.get("widget") or ""), str(o.get("act") or "")) for o in (parte.get("ops") or []) if isinstance(o, dict)]


def complete_probe(reply: str, action: str, parte) -> str:
    """The text channel's reply with the transport receipt it owes appended."""
    line = owed(reply, ops_of_probe(action, parte))
    return f"{str(reply or '').rstrip()} {line}".strip() if line else reply


def voice_owed(reply: str) -> str:
    """The voice channel's owed sentence, from the controls HIS turn ran (`canvas_focus.this_turn_acts`)."""
    try:
        from nucleo import canvas_focus as _cf
        return owed(reply, [(c, a) for c, k, a in _cf.this_turn_acts() if k == "control"])
    except Exception as e:  # noqa: BLE001
        logger.debug(f"transport_receipt: voice acts unread — {e}")
        return ""


# ── 2026-10-11 (ES round, turn 5): the OUTCOME, not the intention ──────────────────────────────────────────────────
# `owed` reads the card the instant the op returned: «Suena ahora «Rick Astley…»» was appended over a `next` the
# embedded player refused a second later, twice (`player_outcome`). The async doors below read what the move ENDED
# in, and a refusal owes its sentence even over a reply that named the title — that reply claimed it was playing.


def _outcome_line(out: dict, lang) -> str:
    refused = [t[:90] for t in (out.get("refused") or ([out.get("title")] if out.get("title") else []))]
    if out.get("state") == "blocked" and refused:
        joined = f"» {lang.receipt_and} «".join(refused)
        return str(lang.receipt_cannot_play).format(title=joined)
    if out.get("state") == "swapped" and out.get("title") and out.get("to"):
        return str(lang.receipt_swapped).format(title=str(out["title"])[:90], to=str(out["to"])[:90])
    return ""


async def owed_settled(reply: str, ops, lang=None, *, min_wait: float = 0.0) -> str:
    """`owed`, with a move on the video player answered by what the player made of it. Never raises."""
    try:
        if lang is None:
            from i18n import langs as _langs
            lang = _langs.current_language()
        from nucleo.flash import player_outcome as _po
        for card, act in ops or []:
            base = str(card or "").split("::", 1)[0].strip().lower()
            if base == "youtube" and str(act or "").strip() in MOVES:
                out = await _po.settled(base, min_wait=min_wait)
                line = _outcome_line(out, lang)
                if line:
                    return line
                break
        return owed(reply, ops, lang)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"transport_receipt: outcome skipped — {type(e).__name__}: {e}")
        return owed(reply, ops, lang)


async def voice_owed_settled(reply: str) -> str:
    """`voice_owed` over the controls that did NOT fail (`canvas_focus.this_turn_acts` drops a refused one), read
    after the detached dispatch has landed and the player has answered."""
    try:
        from nucleo import canvas_focus as _cf
        return await owed_settled(reply, [(c, a) for c, k, a in _cf.this_turn_acts() if k == "control"],
                                  min_wait=0.3)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"transport_receipt: voice acts unread — {e}")
        return ""
