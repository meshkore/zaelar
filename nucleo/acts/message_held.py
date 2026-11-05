"""The held row of the message door (V2-800, CRIT-C9): his order over a row he has SEEN is the yes.

Split out of `nucleo/acts/message.py`, which re-exports every name here (`message.held`, `message.confirmed`, …) — one
door, read the same from Flash and from a worker's exit door. A widget whose action delivers a held row exposes
`held_row(action, payload)` in its data module; the turn's verdict must surely name that very act, and the ONE consent
rule decides with `his_yes=True`. The act itself runs in a worker (V2-852 M2), so the turn records its reading over
that row (`note_his_order`) and the worker's door reads it with no brief.
"""
from __future__ import annotations

import importlib
import time as _time

from loguru import logger

from nucleo.acts.message_names import fold as _fold


def _note(what: str) -> None:
    logger.debug(f"acts.message: {what}")


# ── the held row: his order over what he saw ───────────────────────────────────────────────────────────────

def held(widget_id: str, action: str, payload) -> dict | None:
    """The row this call would deliver, when the widget declares one he has seen — else None. Never raises."""
    wid = str(widget_id or "").split("::", 1)[0].strip().lower()
    if not wid or not action:
        return None
    try:
        hook = getattr(importlib.import_module(f"widgets.{wid}.data"), "held_row", None)
        row = hook(action, dict(payload or {})) if callable(hook) else None
        return row if isinstance(row, dict) and row else None
    except Exception as e:  # noqa: BLE001 — an unreadable hook keeps the friction it had
        logger.info(f"acts.message: {wid}.held_row unreadable ({e}) — the act keeps its question")
        return None


#: His sure orders over a held row, recorded by the turn that routed the act (V2-852 M2): the act runs in a worker,
#: which has no brief of the turn, so the turn's reading travels with the row it was about. Keyed by the row itself
#: (`_row_token`), so a draft edited after his order is another row and is asked again. Bounded; lost on a restart,
#: which only brings the question back.
_HIS_ORDERS: dict[tuple, float] = {}
_HIS_ORDERS_MAX = 32


def _row_token(widget_id: str, action: str, row: dict) -> tuple:
    wid = str(widget_id or "").split("::", 1)[0].strip().lower()
    ident = str(row.get("key") or row.get("id") or "")        # which row …
    body = _fold(str(row.get("text") or ""))[:240]              # … and what he saw in it: an edit is another row
    target = row.get("target") if isinstance(row.get("target"), dict) else {}
    return (wid, str(action or "").strip(), ident, body,
            str(target.get("chatId") or target.get("to") or row.get("to") or ""))


def note_his_order(widget_id: str, action: str, payload, brief) -> bool:
    """Record that the turn surely ordered this act over a held row he has seen — the reading `ordered` needs where no
    brief exists (a worker's exit door). True when recorded. Never raises."""
    try:
        if brief is None or not ordered(widget_id, action, payload, brief):
            return False
        row = held(widget_id, action, payload) or {}
        _HIS_ORDERS[_row_token(widget_id, action, row)] = _time.time()
        for old in sorted(_HIS_ORDERS, key=_HIS_ORDERS.get)[:max(0, len(_HIS_ORDERS) - _HIS_ORDERS_MAX)]:
            _HIS_ORDERS.pop(old, None)
        return True
    except Exception as e:  # noqa: BLE001
        _note(f"his order over the row not recorded ({e!r})")
        return False


def ordered(widget_id: str, action: str, payload, brief) -> bool:
    """A seen held row AND his sure order of this very act: the turn's verdict, or — with no brief, at a worker's door —
    the order the turn that routed it recorded over that same row (`note_his_order`)."""
    row = held(widget_id, action, payload)
    if row is None:
        return False
    if brief is None:
        return _row_token(widget_id, action, row) in _HIS_ORDERS
    from nucleo.flash import undecided as _und
    return _und.sure_order(brief, widget_id, action)


def confirmed(widget_id: str, action: str, payload, brief) -> bool:
    """`ordered`, and the one consent rule runs it with `his_yes` — the reader every gate asks."""
    if not ordered(widget_id, action, payload, brief):
        return False
    try:
        from nucleo import consent
        from nucleo.flash import frontend as _fe
        return not consent.asks(_fe.action_verdict(widget_id, action, payload, his_yes=True))
    except Exception as e:  # noqa: BLE001
        logger.info(f"acts.message: consent unreadable ({e}) — the act keeps its question")
        return False


def release(mode, widget_id: str, action: str, payload, brief):
    """`mode`, or FAST when it is CONFIRM and his order over a row he has seen is the yes."""
    from widgets import actions as _wa
    return _wa.FAST if mode == _wa.CONFIRM and confirmed(widget_id, action, payload, brief) else mode
