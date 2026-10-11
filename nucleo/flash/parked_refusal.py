"""The last data-op a card REFUSED for a missing half, kept for the turn that supplies it.

Video-queue use case, ES round of 2026-10-11 (engine 3.36+d6f4a99f), turns 5-6: «El que está sonando ahora, ese
ponlo el primero» → `youtube:move` refused («Dime a qué posición lo muevo»); he answered «A la 1, ponlo el primero de
todos» — the verdict read `youtube:move` 0.75, the model called nothing and REPEATED the refusal word for word, and the
verdict rung stood down because the reply «asked for a detail» (`undecided`). The question had already been asked
and he had just answered it: the turn was decided by HIM, and nothing held the two halves together.

Two readers, one record, written at the one seam both channels share (`data_ops.corrected_retry` — the voice rail
and the text channel both pass a refusal through it):
  · `last()` gives a payload fill the half the refused call already carried, so his answer completes the parked
    call instead of starting a fresh question;
  · `parrots()` tells `undecided` that a reply which only repeats the card's refusal is not a NEW question.
Stale by construction: a refusal older than the window, or on a card whose data has changed since (a later op
landed), is nobody's parked question any more — the same rule `data_ops.is_identical_retry_of_refused` uses.
"""
from __future__ import annotations

import re
import time
import unicodedata

from loguru import logger

WINDOW_S = 180.0

#: (card base id, action, payload, message, ts, card revision) — or None.
_LAST: dict = {"v": None}


def _base(wid: str) -> str:
    return str(wid or "").split("::", 1)[0].strip().lower()


def _revision(wid: str) -> int:
    try:
        from widgets import store as _store
        return _store.revision(_base(wid))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"parked_refusal: no card revision — {e}")
        return 0


def _fold(text: str) -> str:
    s = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", s))


def remember(wid: str, action: str, payload: dict | None, res, *, now: float | None = None) -> None:
    """Keep this refusal as the parked question; a result that is not a refusal forgets it."""
    try:
        from nucleo.flash import op_receipt as _receipt
        if not isinstance(res, dict) or _receipt.is_pool_timeout(res) or not _receipt.failed(res):
            forget()
            return
        msg = str(res.get("message") or res.get("error") or "").strip()
        _LAST["v"] = (_base(wid), str(action or "").strip(), dict(payload or {}), msg,
                      time.time() if now is None else now, _revision(wid))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"parked_refusal: not remembered — {e}")


def forget() -> None:
    _LAST["v"] = None


def last(wid: str, action: str = "", *, now: float | None = None) -> dict | None:
    """`{action, payload, message}` of the refusal parked on this card (and action, when given), or None."""
    rec = _LAST["v"]
    if not rec:
        return None
    r_wid, r_action, r_payload, r_msg, r_ts, r_rev = rec
    if r_wid != _base(wid) or (action and r_action != str(action or "").strip()):
        return None
    if ((time.time() if now is None else now) - r_ts) > WINDOW_S or _revision(r_wid) != r_rev:
        return None
    return {"action": r_action, "payload": dict(r_payload), "message": r_msg}


def parrots(model_words: str, wid: str, action: str = "", *, now: float | None = None) -> bool:
    """Does the reply only REPEAT the parked refusal's own words? Then it is the card's question re-read, not a new
    one, and his answer in this turn is what decides the turn."""
    rec = last(wid, action, now=now)
    if rec is None:
        return False
    msg = _fold(rec.get("message"))
    return bool(msg) and len(msg.split()) >= 3 and msg in _fold(model_words)
