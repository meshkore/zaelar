"""The turn's RECEIPT: a reply accounts for every card the turn changed (V2-781, `tres-tarjetas-y-el-video-por-alusion`).

Measured ES+EN 2026-10-11, the trailer on `youtube`, calm music on `musica` and the agenda all in play:

  · ES t0 «Ponme el tráiler de Dune, y de fondo algo de música tranquila. Ah, y ábreme la agenda…» — all three cards
    opened, the reply said «Voy con el tráiler y la música.», and the operator asked «¿Y la agenda?».
  · ES t5 «Quita eso y deja la música…» — the video was closed and the reply spoke of the music and of Thursday only;
    he asked twice more whether the video was gone.
  · EN t2/t4/t6/t7 — «Done.» over a volume change, a pause and two closes, with two players open that both declare
    `volume_down` and `pause`. He had to ask which player each time, and the t7 close of the wrong card went unseen
    because nothing said what was left.

One rule, read from what the turn DID (never from what the model says it did): the reply must name

  · every card the turn CLOSED — and then what is still on screen;
  · every card the turn OPENED, when the reply names some of the turn's cards and not others (a reply that names
    none of them — «I'll get all three going» — already speaks for all);
  · the card a CONTROL ran on, when another open card declares the same control («Done on Music.»).

A reply that already names the card is left alone; a content-free one («Done.», «Vale.») is replaced by the
receipt. A card is «named» by what it is called (`naming.catalogue_names`), by the words it declares for itself
(id, name, aliases) and by what it is holding (its `ref_index` labels — «el tráiler» names the player holding the
Dune trailer). The sentences are the language's own (`receipt_*`), the card names its catalogue name.

The text channel completes its reply here (`probe.py`, beside the delivery backstop). The voice channel's words
have already streamed, so — like `delivery.apply_to_reply` — it only takes the receipt where it would have said a
bare ack (`voice_ack`, from the cards the turn touched in `canvas_focus`).
"""
from __future__ import annotations

import re
import unicodedata

from loguru import logger

CLOSE, SHOW, CONTROL = "close", "show", "control"


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _base(card: str) -> str:
    return str(card or "").split("::", 1)[0].strip().lower()


def _open_now() -> list[str]:
    """The cards on screen: what the desktop reported, else the normalised state. `[]` = unknown."""
    try:
        from server.voice_api import open_instances
        ids = [str(i) for i in open_instances() if str(i)]
        if ids:
            return ids
        from memory import api as _memapi
        return [str(w) for w in ((_memapi.state() or {}).get("open_widgets") or []) if str(w)]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"card_receipt: screen unread — {e}")
        return []


def card_name(card: str, code: str = "") -> str:
    """What the card is called in the reply's language («Música», «Calendar»), else its manifest name, else its id."""
    base = _base(card)
    try:
        from i18n import runtime as _i18n_rt
        name = str(_i18n_rt.text(f"widgets.{base}.name", "", code=code or None) or "")
        if name:
            return name
    except Exception as e:  # noqa: BLE001
        logger.debug(f"card_receipt: bundle name unread — {e}")
    try:
        from widgets import runtime as _rt
        return str((_rt.get(base) or {}).get("name") or base)
    except Exception:  # noqa: BLE001
        return base


def display_label(label: str, code: str = "") -> str:
    """A `which_card` label («youtube — paused») with its id shown as the card's display name («YouTube — paused»)."""
    wid, sep, rest = str(label or "").partition(" — ")
    return card_name(wid, code) + sep + rest if wid else str(label or "")


def _words_of(card: str) -> list[str]:
    base = _base(card)
    words: list[str] = [base]
    try:
        from widgets import naming as _naming
        from widgets import runtime as _rt
        man = _rt.get(base) or {}
        words += list(_naming.catalogue_names(base)) + [str(man.get("name") or ""), str(man.get("title") or "")]
        words += [str(a) for a in (man.get("aliases") or [])]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"card_receipt: names unread — {e}")
    try:
        from widgets import refs as _refs
        for row in (_refs._ref_index(base) or [])[:3]:
            words += [w for w in re.findall(r"\w+", str((row or {}).get("label") or "")) if len(w) >= 5]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"card_receipt: rows unread — {e}")
    return [w for w in {_norm(x).strip() for x in words} if len(w) >= 3]


def names(reply: str, card: str) -> bool:
    """Does the reply name this card — by what it is called, declares, or holds?"""
    t = _norm(reply)
    return bool(t) and any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", t) for w in _words_of(card))


def content_free(reply: str) -> bool:
    """An ack that says nothing about any card: empty, the engine's own «Done.», or two words with no number."""
    r = str(reply or "").strip()
    if not r:
        return True
    try:
        from nucleo.flash import dialog as _dialog
        if _dialog._is_silent_ack(r):
            return True
    except Exception as e:  # noqa: BLE001
        logger.debug(f"card_receipt: ack set unread — {e}")
    words = re.findall(r"\w+", r)
    return len(words) <= 2 and not any(w.isdigit() for w in words)


def _shared(card: str, action: str, open_ids) -> bool:
    """Does ANOTHER open card declare this same control?"""
    try:
        from nucleo.flash import frontend as _fe
        return any(_base(o) != _base(card) and action in (_fe.declared_actions(_base(o)) or {}) for o in open_ids or [])
    except Exception:  # noqa: BLE001
        return False


def _join(lang, cards) -> str:
    names_ = [card_name(c, getattr(lang, "code", "")) for c in cards]
    if len(names_) <= 1:
        return "".join(names_)
    return ", ".join(names_[:-1]) + f" {getattr(lang, 'receipt_and', 'y')} " + names_[-1]


def lines_for(reply: str, acts, *, open_ids=None, lang=None) -> list[str]:
    """The receipt's sentences this reply still owes, in order. `[]` when it owes none. Never raises."""
    try:
        if not acts:
            return []
        if lang is None:
            from i18n import langs as _langs
            lang = _langs.current_language()
        ids = _open_now() if open_ids is None else [str(i) for i in open_ids or []]
        free = content_free(reply)
        closed = [c for c, k, _ in acts if k == CLOSE]
        shown = [c for c, k, _ in acts if k == SHOW]
        out: list[str] = []
        if closed:
            missing = [c for c in closed if free or not names(reply, c)]
            gone = {_base(c) for c in closed}
            left = list(dict.fromkeys(_base(c) for c in ids + shown if _base(c) not in gone))
            if missing:
                out.append(lang.receipt_closed.format(cards=_join(lang, missing)))
            if ids and (missing or not any(names(reply, c) for c in left)):   # an unknown screen says nothing of it
                out.append(lang.receipt_left.format(cards=_join(lang, left)) if left else lang.receipt_left_none)
        if shown and not free and len(acts) >= 2 and any(names(reply, c) for c, _, _ in acts):
            missing = [c for c in shown if not names(reply, c)]
            if missing:
                out.append(lang.receipt_opened.format(cards=_join(lang, missing)))
        for card, kind, act in acts:
            if kind == CONTROL and _shared(card, act, ids) and (free or not names(reply, card)):
                out.append(lang.receipt_on_card.format(cards=card_name(card, getattr(lang, "code", ""))))
        return out
    except Exception as e:  # noqa: BLE001
        logger.debug(f"card_receipt: skipped — {type(e).__name__}: {e}")
        return []


def complete(reply: str, acts, *, open_ids=None, lang=None) -> str:
    """The reply with the receipt it owes: appended to a reply with content, in place of a content-free one."""
    lines = lines_for(reply, acts, open_ids=open_ids, lang=lang)
    if not lines:
        return reply
    return " ".join(lines) if content_free(reply) else f"{str(reply).rstrip()} {' '.join(lines)}"


def voice_ack(ack: str) -> str:
    """The voice channel's bare ack, replaced by the receipt of the cards this turn touched (`canvas_focus`)."""
    try:
        from nucleo import canvas_focus as _cf
        from nucleo.flash import worker_note_relay as _relay   # his words went to the worker: say what follows
        return _relay.voice_line(_cf.this_turn_acts()) or complete(ack, _cf.this_turn_acts()) or ack
    except Exception as e:  # noqa: BLE001
        logger.debug(f"card_receipt: voice ack kept — {e}")
        return ack
