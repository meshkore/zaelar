"""A close that names no card closes the OTHERS — never the card he is working on (V2-807 T-08).

THE DEFECT. «Close whatever you don't need right now» closed every card, the draft he had just corrected included: the
model's «keep the document» was a discarded `show_widget`, and a bare close reached the client as `closeAll()`.

THE CLASS. A bulk close (one that names no card) closes the cards he is NOT using; the one in use stays unless his
words name it. «In use» is read from facts: the WORKING card (the newest open card a data-op ran on, `done_ops`, within
`WORKING_S`) and a card the turn KEPT (a show of an open card during a close turn, `note_kept`, for `KEPT_S`). Nothing
in use, or an unknown canvas → the bare `closeAll()`, as before.

A SPARE NEVER EMPTIES THE ORDER (V2-812 T-04: «ciérralo todo» spared the only open card, in silence): when sparing would
leave nothing to close, everything closes. Every bulk close leaves its RECEIPT (`receipt()`), said by the doors that
have no model reply of their own (the hard interrupt, the action map).

AN EXPLICIT TOTAL SPARES NOTHING (V2-831 T-02): `scope="all"` from the grammar, or the closed question when it read none.

Every bulk-close door of a TURN goes through `close_all`; the reset endpoints do not (a reset is the lifecycle).
"""
from __future__ import annotations

import time

from loguru import logger

#: How long a data-op keeps its card «in use» (a draft corrected a minute ago is; a card touched ten minutes ago is not).
WORKING_S = 300.0
#: How long a model's «keep this one» lasts — the rest of the same sentence, which may arrive as the next fragment.
KEPT_S = 30.0

_KEPT: dict[str, float] = {}
#: The last bulk close: what it closed, what it kept, what was open, when — read once by `take_receipt`.
_LAST: dict = {}
#: How long a bulk close's receipt is owed — the same turn, never a later one.
RECEIPT_S = 20.0


def _base(card: str) -> str:
    return str(card or "").split("::", 1)[0].strip().lower()


def note_kept(card: str) -> None:
    """The turn chose to KEEP `card` while closing others — a bulk close in the next `KEPT_S` spares it."""
    c = str(card or "").strip().lower()
    if c:
        _KEPT[c] = time.time()


def kept_now() -> list[str]:
    """The cards a recent turn chose to keep, still within `KEPT_S`."""
    now = time.time()
    for c in [c for c, at in _KEPT.items() if now - at > KEPT_S]:
        _KEPT.pop(c, None)
    return list(_KEPT)


def reset() -> None:
    """Forget every keep and the last receipt (tests, session reset)."""
    _KEPT.clear()
    _LAST.clear()


def _on_canvas(card: str, open_ids) -> str:
    """The open card `card` designates: itself when open, else the one open instance of its piece, else ""."""
    c = str(card or "").strip().lower()
    opened = [str(o or "").strip() for o in (open_ids or []) if str(o or "").strip()]
    if c in {o.lower() for o in opened}:
        return next(o for o in opened if o.lower() == c)
    same = [o for o in opened if _base(o) == _base(c)]
    return same[0] if len(same) == 1 else ""


def working_card(open_ids, *, within_s: float = WORKING_S) -> str:
    """The open card a data-op most recently RAN on, within `within_s` — "" when none is open."""
    try:
        from nucleo import done_ops as _done
        for row in reversed(_done.recent(within_s=within_s, limit=40)):
            hit = _on_canvas(str(row.get("wid") or ""), open_ids)
            if hit:
                return hit
    except Exception as e:  # noqa: BLE001
        logger.debug(f"bulk_close: working card unreadable — {e}")
    return ""


def in_use(open_ids, text: str = "") -> list[str]:
    """The open cards a bulk close must spare: the working card and the kept ones, minus any his words NAME."""
    spare: list[str] = []
    for c in [working_card(open_ids)] + kept_now():
        hit = _on_canvas(c, open_ids) if c else ""
        if hit and hit not in spare:
            spare.append(hit)
    if spare and text:
        try:
            from widgets import instances as _inst
            named = {_base(x) for x in _inst.named_in(text, spare)}
            spare = [c for c in spare if _base(c) not in named]
        except Exception as e:  # noqa: BLE001
            logger.debug(f"bulk_close: naming unreadable — {e}")
    return spare


def spare_for(opened, text: str = "", *, emit=None, src: str = "", scope: str = "") -> list[str]:
    """The cards a bulk close over `opened` keeps: the ones in use — unless keeping them leaves NOTHING to close,
    or his words closed them ALL (`scope="all"`).

    V2-812 T-04: a close-all whose every open card is «in use» is an order about those very cards, so none is kept.
    Sparing exists to protect the draft among OTHER cards, never to turn «close everything» into a no-op."""
    spare = in_use(opened, text) if opened else []
    if spare and scope != "all" and _closes_every_card(text, spare):
        scope = "all"                        # the grammar read no total; the closed question did (Z2, pass 4)
    if spare and scope == "all":
        if emit is not None:
            emit("brain", "🧷 bulk close: an explicit total — the card in use closes too", text=",".join(spare),
                 role="system", extra={"cat": "flash", "would_keep": spare, "src": src, "scope": scope})
        return []
    if spare and not [c for c in opened if c not in spare]:
        if emit is not None:
            emit("brain", "🧷 bulk close: sparing would close nothing — everything closes", text=",".join(spare),
                 role="system", extra={"cat": "flash", "would_keep": spare, "src": src})
        return []
    return spare


def _closes_every_card(text: str, spare) -> bool:
    """ONE closed question, only when a bulk close would spare a card in use and the grammar read no total: does he close
    that card too? (pass 4 Z2: «clear everything off the screen» spared Images.) No answer keeps the spare."""
    try:
        from nucleo import jev
        q = {"scope": {"instructions": f"The card he was using: «{', '.join(spare)}». Does he close that one too?",
                       "criteria": {"every_card": "yes, every card off the screen", "spare": "no, only the others"}}}
        got = jev.choose_many_sync(f"The operator said «{str(text).strip()[:300]}».", q, question_id="close_scope") if str(text or "").strip() else {}
        return float((((got or {}).get("scope") or {}).get("probs") or {}).get("every_card") or 0.0) >= jev.MIN_CONFIDENCE
    except Exception as e:  # noqa: BLE001 — unaskable: the spare stays
        return bool(logger.debug(f"bulk_close: scope question not asked — {e!r}"))


def _open_instances() -> list[str]:
    try:
        from server.voice_api import open_instances
        return list(open_instances() or [])
    except Exception as e:  # noqa: BLE001
        logger.debug(f"bulk_close: canvas unreadable — {e}")
        return []


def close_all(emit, *, src: str, text: str = "", said: str = "", extra: dict | None = None,
              open_ids=None, brief=None, scope: str = "") -> list[str]:
    """Close every card he is not using. Returns the cards spared ([] = the bare close-all went out).

    `text` is his sentence (read to see whether it names a card in use); `said` is the phrase a caller already
    attaches to its canvas events (the action map does), passed through unchanged; `scope="all"` spares nothing. Each
    close crosses the canvas door with the turn (`brief`, his sentence)."""
    from nucleo.acts import canvas_turn
    from nucleo.acts import canvas
    base = {k: v for k, v in (extra or {}).items() if k not in ("id", "src")}
    req = canvas_turn.request_of(brief, text)
    opened = list(open_ids) if open_ids is not None else _open_instances()
    spare = spare_for(opened, text, emit=emit, src=src, scope=scope)
    if not spare:
        if canvas.apply("close", "", src=src, text=said, emit=emit, request=req, **base):
            _note(closed=opened, kept=[], opened=opened)
        return []
    for cid in opened:
        if cid not in spare:
            canvas.apply("close", cid, src=src, text=said, emit=emit, request=req, **base)
    emit("brain", "🧷 bulk close: the card in use stays", text=",".join(spare), role="system",
         extra={"cat": "flash", "kept": spare, "src": src})
    _note(closed=[c for c in opened if c not in spare], kept=spare, opened=opened)
    return spare


def _note(*, closed, kept, opened) -> None:
    _LAST.clear()
    _LAST.update({"closed": list(closed), "kept": list(kept), "opened": list(opened), "at": time.time()})


def receipt(closed, kept, *, opened=None, lang=None) -> str:
    """One short line in his language: what a bulk close closed, and what is still on screen.

    Built from the language's own receipt sentences (`receipt_closed` · `receipt_left` · `receipt_left_none`), the
    cards named by their display names, never by id. With an unknown canvas (nothing reported) the bare close took
    whatever was there: all that can be said truthfully is that nothing is left."""
    try:
        from nucleo.flash import card_receipt as _cr
        if lang is None:
            from i18n import langs as _langs
            lang = _langs.current_language()
        gone = list(dict.fromkeys(_base(c) for c in closed or [] if _base(c)))
        left = [_base(c) for c in dict.fromkeys(kept or []) if _base(c) and _base(c) not in gone]
        left = list(dict.fromkeys(left))
        if not gone:
            return "" if left else str(lang.receipt_left_none or "")
        line = [lang.receipt_closed.format(cards=_cr._join(lang, gone))]
        line.append(lang.receipt_left.format(cards=_cr._join(lang, left)) if left else lang.receipt_left_none)
        return " ".join(x for x in line if x)
    except Exception as e:  # noqa: BLE001 — a receipt never breaks the close it describes
        logger.debug(f"bulk_close: receipt unbuilt — {e}")
        return ""


def take_receipt(*, within_s: float = RECEIPT_S) -> str:
    """The receipt of the bulk close this turn just made, ONCE ("" when none, or when it is stale)."""
    last = dict(_LAST)
    _LAST.clear()
    if not last or time.time() - float(last.get("at") or 0) > within_s:
        return ""
    return receipt(last.get("closed"), last.get("kept"), opened=last.get("opened"))
